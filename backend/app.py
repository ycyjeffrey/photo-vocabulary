import asyncio
import hashlib
import json
import logging
import os
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import model, ocr
from .images import MAX_BYTES, decode_image, image_hash, preprocess
from .layout import structure
from .schemas import Card, CardRequest, EnrichRequest, ExtractionRequest
from .store import Store
from .validation import validate_cards

ROOT = Path(__file__).resolve().parents[1]
PIPELINE_VERSION = "tesseract-eng-paddleocr-v5-chinese-v1"
LOGGER = logging.getLogger(__name__)
ALLOWED_ORIGINS = {
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:8000", "http://127.0.0.1:8000",
}


class BodyTooLarge(Exception):
    pass


class LocalRequestMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        origin = headers.get(b"origin", b"").decode()
        if origin and origin not in ALLOWED_ORIGINS:
            await JSONResponse({"detail": "Only the local application may access this API."},
                               status_code=403)(scope, receive, send)
            return
        limit = MAX_BYTES + 65536 if scope["path"] == "/v1/images" else 4 * 1024 * 1024
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            await JSONResponse({"detail": "Invalid Content-Length."}, status_code=400)(scope, receive, send)
            return
        if length > limit:
            await JSONResponse({"detail": "Request exceeds the upload size limit."},
                               status_code=413)(scope, receive, send)
            return
        consumed = 0

        async def limited_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get("body", b""))
            if consumed > limit:
                raise BodyTooLarge()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except BodyTooLarge:
            await JSONResponse({"detail": "Request exceeds the upload size limit."},
                               status_code=413)(scope, receive, send)


def create_app(data_dir: Path | None = None, recognizer=None) -> FastAPI:
    root = data_dir or Path(os.environ.get("DATA_DIR", str(ROOT / "data")))
    store = Store(root)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vocabulary-worker")
    lock = threading.RLock()

    @asynccontextmanager
    async def lifespan(app):
        yield
        executor.shutdown(wait=True, cancel_futures=False)

    app = FastAPI(title="Photo Vocabulary", version="1.0.0", lifespan=lifespan)
    app.state.store = store
    app.add_middleware(CORSMiddleware, allow_origins=list(ALLOWED_ORIGINS),
                       allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type"])
    app.add_middleware(LocalRequestMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])

    def get_image(image_id: str):
        image = store.image(image_id)
        if not image:
            raise HTTPException(404, "Image not found.")
        return image

    def get_extraction(extraction_id: str):
        result = store.extraction(extraction_id)
        if not result:
            raise HTTPException(404, "Extraction not found.")
        return result

    def completed(extraction_id: str):
        result = get_extraction(extraction_id)
        if result["status"] != "completed":
            raise HTTPException(409, "Extraction is not completed.")
        return result

    def process(payload: dict, cache_key: str, request: ExtractionRequest):
        start = time.monotonic()

        def stage(status: str):
            payload["status"] = status
            store.save_extraction(payload, cache_key)

        try:
            stage("preprocessing")
            output = root / f"{payload['id']}.png"
            payload["transform"] = preprocess(root / f"{request.imageId}.png", output, request)
            stage("recognizing")
            if recognizer:
                store.bump("ocrCalls")
                blocks = recognizer(output)
            else:
                blocks = ocr.recognize(output, request.layout, lambda: store.bump("ocrCalls"))
            stage("structuring")
            cards, warnings = structure(blocks, payload["transform"]["processedSize"][0], request.layout)
            if not recognizer and any(b.language == "chi_tra+eng" for b in blocks):
                warnings.append(
                    "部分區域無法確認英中分隔，仍保留混合 OCR 初讀結果。"
                    "請選擇「左英文｜右中文」並調整裁切，以使用英文 Tesseract／中文 PaddleOCR 分開辨識。"
                )
            payload.update(
                ocr_blocks=[b.model_dump() for b in blocks],
                draft_cards=[c.model_dump() for c in cards], warnings=warnings,
                processedUrl=f"/v1/extractions/{payload['id']}/image",
                elapsedMs=round((time.monotonic() - start) * 1000), error=None,
            )
            stage("completed")
        except Exception as exc:
            # Persist unexpected worker failures so polling clients never hang indefinitely.
            LOGGER.exception("Extraction %s failed", payload["id"])
            payload.update(error=f"Extraction failed: {exc}",
                           elapsedMs=round((time.monotonic() - start) * 1000))
            stage("failed")

    @app.get("/v1/health")
    def health():
        ready, message = ocr.readiness()
        try:
            _, configured_model = model.settings()
            model_message = "Local model configured" if configured_model else "Optional local model not configured"
        except ValueError as exc:
            configured_model = ""
            model_message = str(exc)
        return {"ocrReady": ready, "ocrMessage": message, "modelConfigured": bool(configured_model),
                "modelMessage": model_message, "metrics": store.metrics(), "pipelineVersion": PIPELINE_VERSION}

    @app.get("/v1/library")
    def library():
        with store.connect() as db:
            images = [dict(row) for row in db.execute("SELECT * FROM images ORDER BY rowid DESC")]
            extractions = [json.loads(row["payload"]) for row in db.execute(
                "SELECT payload FROM extractions ORDER BY rowid DESC"
            )]
        return {"images": [
            {**image, "previewUrl": f"/v1/images/{image['id']}/preview"} for image in images
        ], "extractions": [
            {key: item[key] for key in ("id", "imageId", "status")} for item in extractions
        ]}

    @app.post("/v1/images", status_code=201)
    async def upload_image(file: UploadFile = File(...)):
        try:
            data = await file.read(MAX_BYTES + 1)
        finally:
            await file.close()
        try:
            image = await asyncio.to_thread(decode_image, data)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        image_id = uuid.uuid4().hex
        original_suffix = ".jpg" if data.startswith(b"\xff\xd8") else ".png"
        with lock:
            (root / f"{image_id}.original{original_suffix}").write_bytes(data)
            image.save(root / f"{image_id}.png", "PNG")
            with store.connect() as db:
                db.execute("INSERT INTO images VALUES (?, ?, ?, ?)",
                           (image_id, image_hash(image), image.width, image.height))
        return {"imageId": image_id, "width": image.width, "height": image.height,
                "previewUrl": f"/v1/images/{image_id}/preview"}

    @app.get("/v1/images/{image_id}/preview")
    def preview(image_id: str):
        get_image(image_id)
        return FileResponse(root / f"{image_id}.png", media_type="image/png",
                            headers={"Cache-Control": "no-store"})

    @app.post("/v1/extractions", status_code=202)
    def extract(request: ExtractionRequest):
        with lock:
            image = get_image(request.imageId)
            config = request.model_dump(exclude={"imageId"})
            cache_key = hashlib.sha256(json.dumps(
                [image["hash"], config, PIPELINE_VERSION, ocr.configuration(), ocr.model_signature()], sort_keys=True
            ).encode()).hexdigest()
            with store.connect() as db:
                cached = db.execute(
                    "SELECT payload FROM extractions WHERE cache_key=? AND status='completed' LIMIT 1",
                    (cache_key,),
                ).fetchone()
                active = db.execute(
                    "SELECT count(*) FROM extractions WHERE status NOT IN ('completed', 'failed')"
                ).fetchone()[0]
            extraction_id = uuid.uuid4().hex
            if cached:
                payload = json.loads(cached["payload"])
                source_id = payload["id"]
                shutil.copyfile(root / f"{source_id}.png", root / f"{extraction_id}.png")
                payload.pop("reviewed_cards", None)
                payload.update(id=extraction_id, imageId=request.imageId, cacheHit=True, elapsedMs=0,
                               processedUrl=f"/v1/extractions/{extraction_id}/image")
                store.bump("cacheHits")
                store.save_extraction(payload, cache_key)
                return payload
            if active >= 8:
                raise HTTPException(429, "The local queue is full. Wait for current work to finish.")
            if recognizer is None:
                ready, message = ocr.readiness()
                if not ready:
                    raise HTTPException(503, message)
            payload = {
                "id": extraction_id, "imageId": request.imageId, "status": "queued",
                "settings": config, "ocr_blocks": [], "draft_cards": [], "warnings": [],
                "pipeline_version": PIPELINE_VERSION, "cacheHit": False, "elapsedMs": 0,
                "error": None,
            }
            store.save_extraction(payload, cache_key)
            executor.submit(process, payload.copy(), cache_key, request)
            return payload

    @app.get("/v1/extractions/{extraction_id}")
    def extraction(extraction_id: str):
        return get_extraction(extraction_id)

    @app.get("/v1/extractions/{extraction_id}/image")
    def processed_image(extraction_id: str):
        completed(extraction_id)
        return FileResponse(root / f"{extraction_id}.png", media_type="image/png",
                            headers={"Cache-Control": "no-store"})

    @app.post("/v1/cards/validate")
    def validate(request: CardRequest):
        return validate_cards(request.cards, completed(request.extractionId))

    @app.put("/v1/extractions/{extraction_id}/cards")
    def save_cards(extraction_id: str, request: CardRequest):
        if request.extractionId != extraction_id:
            raise HTTPException(400, "Extraction IDs do not match.")
        with lock:
            result = completed(extraction_id)
            if len({c.id for c in request.cards}) != len(request.cards):
                raise HTTPException(400, "Card IDs must be unique.")
            known = {b["id"] for b in result["ocr_blocks"]}
            if any(set(c.source_block_ids) - known for c in request.cards):
                raise HTTPException(400, "Unknown source block IDs.")
            result["reviewed_cards"] = [c.model_dump() for c in request.cards]
            with store.connect() as db:
                db.execute("UPDATE extractions SET payload=? WHERE id=?",
                           (json.dumps(result, ensure_ascii=False), extraction_id))
        return {"saved": True}

    @app.post("/v1/cards/enrich")
    async def enrich(request: EnrichRequest):
        original = completed(request.extractionId)
        if len({c.id for c in request.cards}) != len(request.cards):
            raise HTTPException(400, "Card IDs must be unique.")
        original_cards = {c["id"]: Card.model_validate(c) for c in original["draft_cards"]}
        fields_by_id = {c.id: model.missing_fields(c, original_cards.get(c.id)) for c in request.cards}
        candidates = [c for c in request.cards if c.confirmed and c.term.strip() and fields_by_id[c.id]]
        if not candidates:
            raise HTTPException(400, "Confirm an English term with a missing definition or part of speech first. Photo content is never overwritten.")
        try:
            _, configured_model = model.settings()
            if not configured_model:
                raise ValueError("Set OLLAMA_MODEL to enable the optional local model.")
            store.bump("modelCalls")
            enriched = await asyncio.get_running_loop().run_in_executor(
                executor, model.enrich, candidates, fields_by_id,
            )
        except (ValueError, httpx.HTTPError, KeyError) as exc:
            LOGGER.warning("Local enrichment failed: %s", exc)
            raise HTTPException(502, f"Local enrichment failed: {exc}") from exc
        updates = {c.id: c for c in enriched}
        return {"cards": [updates.get(c.id, c) for c in request.cards]}

    @app.delete("/v1/images/{image_id}")
    def delete_image(image_id: str):
        with lock:
            get_image(image_id)
            with store.connect() as db:
                jobs = db.execute("SELECT id, status FROM extractions WHERE image_id=?", (image_id,)).fetchall()
                if any(job["status"] not in {"completed", "failed"} for job in jobs):
                    raise HTTPException(409, "Wait for this photo's extraction to finish before deleting it.")
                for path in (
                    root / f"{image_id}.png", root / f"{image_id}.original.jpg",
                    root / f"{image_id}.original.png",
                    *(root / f"{job['id']}.png" for job in jobs),
                ):
                    path.unlink(missing_ok=True)
                db.execute("DELETE FROM images WHERE id=?", (image_id,))
        return {"deleted": True}

    frontend_dist = ROOT / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    return app


app = create_app()
