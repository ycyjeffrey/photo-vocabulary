import io
import threading
import time
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app import create_app
from backend.images import decode_image, preprocess
from backend.layout import structure
from backend.schemas import Block, Card, Crop, ExtractionRequest
from backend.store import Store
from backend.validation import validate_cards


def block(block_id, text, x, y, width=100, score=0.98):
    return Block(id=block_id, text=text, bbox=(x, y, x + width, y + 25), ocr_score=score)


def sample_blocks():
    return [
        block("b1", "conserve", 30, 30, 140),
        block("b2", "v.", 180, 30, 30),
        block("b3", "節省；保護", 240, 30, 170),
        block("b4", "habitat", 30, 100, 140),
        block("b5", "n.", 180, 100, 30),
        block("b6", "棲息地", 240, 100, 120),
    ]


def png(size=(900, 400)):
    image = Image.new("RGB", size, "white")
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def upload(client):
    result = client.post("/v1/images", files={"file": ("photo.png", png(), "image/png")})
    assert result.status_code == 201, result.text
    return result.json()["imageId"]


def wait_for_job(client, job_id):
    for _ in range(200):
        result = client.get(f"/v1/extractions/{job_id}").json()
        if result["status"] in {"completed", "failed"}:
            return result
        time.sleep(0.02)
    pytest.fail("Extraction did not complete")


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path, recognizer=lambda path: sample_blocks())) as client:
        yield client


def test_single_column():
    cards, warnings = structure(sample_blocks(), 900, "single")
    assert [(c.term, c.part_of_speech, c.definition) for c in cards] == [
        ("conserve", "v.", "節省；保護"), ("habitat", "n.", "棲息地"),
    ]
    assert not warnings
    assert all(c.selected and not c.confirmed and not c.needs_review for c in cards)


@pytest.mark.parametrize("layout", ["auto", "double"])
def test_double_column_never_interleaves(layout):
    blocks = sample_blocks()
    blocks += [b.model_copy(update={
        "id": f"right-{b.id}",
        "bbox": (b.bbox[0] + 900, b.bbox[1], b.bbox[2] + 900, b.bbox[3]),
        "text": {"conserve": "protect", "habitat": "forest"}.get(b.text, b.text),
    }) for b in sample_blocks()]
    cards, warnings = structure(blocks, 1800, layout)
    assert [c.term for c in cards] == ["conserve", "habitat", "protect", "forest"]
    assert [c.definition for c in cards] == ["節省；保護", "棲息地"] * 2
    assert not warnings


def test_wrapped_definition_stays_in_column():
    blocks = sample_blocks()
    blocks[2] = block("b3", "節省；", 240, 30)
    blocks.append(block("b7", "保護", 240, 63))
    blocks.append(block("b8", "不相關標題", 10, 190))
    cards, warnings = structure(blocks, 900, "single")
    assert cards[0].definition == "節省；保護"
    assert "b7" in cards[0].source_block_ids
    assert cards[1].definition == "棲息地"
    assert any("Unpaired" in warning for warning in warnings)


def test_low_score_continuation_requires_review():
    blocks = sample_blocks()
    blocks.append(block("wrapped", "更多釋義", 240, 63, score=0.3))
    cards, _ = structure(blocks, 900, "single")
    assert cards[0].needs_review and not cards[0].selected
    assert "wrapped definition" in cards[0].review_reason


def test_missing_definition_low_score_and_missed_text():
    blocks = [
        block("header", "Vocabulary", 30, 0),
        block("num", "1.", 0, 40, 20),
        block("a", "resource", 30, 40, score=0.5),
        block("pos", "n.", 180, 40),
        block("sentence", "This is a complete example sentence.", 30, 95, 600),
    ]
    cards, warnings = structure(blocks, 900, "single")
    assert len(cards) == 1
    assert cards[0].term == "resource"
    assert cards[0].definition == ""
    assert cards[0].needs_review and not cards[0].selected
    assert "Low OCR" in cards[0].review_reason
    assert "example sentence" in cards[0].example
    assert any("[header]" in warning for warning in warnings)


def test_crop_rotation_and_coordinate_space(tmp_path):
    original = tmp_path / "original.png"
    processed = tmp_path / "processed.png"
    image = Image.new("RGB", (100, 200), "white")
    image.putpixel((0, 0), (255, 0, 0))
    image.save(original)
    result = preprocess(original, processed, ExtractionRequest(
        imageId="photo", rotation=90, crop=Crop(x=0.5, y=0, width=0.5, height=1),
    ))
    assert result["rotatedSize"] == (200, 100)
    assert result["cropBox"] == (100, 0, 200, 100)
    assert result["processedSize"] == (100, 100)
    assert result["coordinateSpace"] == "processed-image"
    with Image.open(processed) as output:
        assert output.getpixel((99, 0)) == (255, 0, 0)
    with Image.open(original) as untouched:
        assert untouched.size == (100, 200)


def test_exif_and_alpha():
    output = io.BytesIO()
    image = Image.new("RGB", (30, 60), "white")
    exif = image.getexif()
    exif[274] = 6
    image.save(output, "JPEG", exif=exif)
    assert decode_image(output.getvalue()).size == (60, 30)
    output = io.BytesIO()
    Image.new("RGBA", (30, 30), (0, 0, 0, 0)).save(output, "PNG")
    assert decode_image(output.getvalue()).getpixel((0, 0)) == (255, 255, 255)


def test_invalid_and_large_images(client, monkeypatch):
    assert client.post("/v1/images", files={"file": ("fake.png", b"not an image")}).status_code == 400
    monkeypatch.setattr("backend.images.MAX_PIXELS", 100)
    assert client.post("/v1/images", files={"file": ("large.png", png())}).status_code == 400
    result = client.post("/v1/extractions", json={
        "imageId": "x", "crop": {"x": 0.9, "y": 0, "width": 0.5, "height": 1},
    })
    assert result.status_code == 422
    assert client.post("/v1/images", headers={"Content-Length": str(20 * 1024 * 1024)}).status_code == 413


def test_export_requires_confirmation_and_sanitizes_fields():
    blocks = sample_blocks()
    cards, _ = structure(blocks, 900, "single")
    result = {"ocr_blocks": [b.model_dump() for b in blocks],
              "draft_cards": [c.model_dump() for c in cards]}
    assert not validate_cards(cards, result)["valid"]
    cards[0].confirmed = True
    cards[0].term = "conserve\tword\n"
    cards[0].definition = "節省\r\n保護"
    cards[1].selected = False
    validation = validate_cards(cards, result)
    assert validation["valid"]
    assert validation["tsv"] == "conserve word\tv. 節省 保護"
    assert any("Spelling" in warning for issue in validation["issues"] for warning in issue["warnings"])


def test_unknown_sources_duplicates_and_manual_cards():
    blocks = sample_blocks()
    cards, _ = structure(blocks, 900, "single")
    original = {"ocr_blocks": [b.model_dump() for b in blocks],
                "draft_cards": [c.model_dump() for c in cards]}
    cards[0].confirmed = True
    cards[0].source_block_ids.append("unknown")
    assert not validate_cards(cards, original)["valid"]
    cards[0].source_block_ids.remove("unknown")
    duplicate = cards[0].model_copy(update={"id": "duplicate"})
    result = validate_cards([cards[0], duplicate], original)
    assert any("more than one" in warning for issue in result["issues"] for warning in issue["warnings"])
    manual = Card(id="manual", term="added", definition="新增", definitionOrigin="manual",
                  selected=True, confirmed=True)
    assert validate_cards([manual], original)["valid"]
    generated_manual = manual.model_copy(update={
        "definitionOrigin": "model", "part_of_speech": "v.", "partOfSpeechOrigin": "model",
    })
    checked = validate_cards([generated_manual], original)
    assert checked["valid"] and checked["tsv"] == "added\tv. 新增"
    assert any("Generated part of speech" in note for issue in checked["issues"] for note in issue["warnings"])
    edited = cards[0].model_copy(update={"definitionOrigin": "manual", "source_block_ids": []})
    assert not validate_cards([edited], original)["valid"]


def test_cache_save_restart_and_delete(client, tmp_path):
    image_id = upload(client)
    response = client.post("/v1/extractions", json={"imageId": image_id, "layout": "single"})
    assert response.status_code == 202
    result = wait_for_job(client, response.json()["id"])
    assert result["status"] == "completed"
    assert client.get(result["processedUrl"]).status_code == 200
    cards = result["draft_cards"]
    for card in cards:
        card["confirmed"] = True
    body = {"extractionId": result["id"], "cards": cards}
    assert client.put(f"/v1/extractions/{result['id']}/cards", json=body).status_code == 200
    validated = client.post("/v1/cards/validate", json=body).json()
    assert validated["valid"] and validated["selectedCount"] == 2
    assert validated["tsv"].splitlines() == ["conserve\tv. 節省；保護", "habitat\tn. 棲息地"]
    second_image = upload(client)
    cached = client.post("/v1/extractions", json={"imageId": second_image, "layout": "single"}).json()
    assert cached["cacheHit"] and cached["imageId"] == second_image
    assert "reviewed_cards" not in cached
    assert client.get("/v1/health").json()["metrics"]["ocrCalls"] == 1
    restored = Store(tmp_path).extraction(result["id"])
    assert restored["reviewed_cards"][0]["confirmed"]
    assert client.delete(f"/v1/images/{image_id}").status_code == 200
    assert client.get(result["processedUrl"]).status_code == 404
    assert client.get(cached["processedUrl"]).status_code == 200
    assert client.delete(f"/v1/images/{second_image}").status_code == 200
    assert not list(tmp_path.glob("*.png"))
    assert client.get("/v1/library").json() == {"images": [], "extractions": []}


def test_changed_settings_do_not_hit_cache(client):
    image_id = upload(client)
    first = client.post("/v1/extractions", json={"imageId": image_id}).json()
    wait_for_job(client, first["id"])
    second = client.post("/v1/extractions", json={"imageId": image_id, "rotation": 180}).json()
    assert not second["cacheHit"]
    wait_for_job(client, second["id"])
    assert client.get("/v1/health").json()["metrics"]["ocrCalls"] == 2


def test_worker_failure_is_visible(tmp_path):
    def fail(path):
        raise RuntimeError("OCR test failure")

    with TestClient(create_app(tmp_path, recognizer=fail)) as client:
        image_id = upload(client)
        job = client.post("/v1/extractions", json={"imageId": image_id}).json()
        result = wait_for_job(client, job["id"])
        assert result["status"] == "failed" and "OCR test failure" in result["error"]


def test_restart_interrupts_pending_jobs(tmp_path):
    store = Store(tmp_path)
    with store.connect() as db:
        db.execute("INSERT INTO images VALUES ('image', 'hash', 1, 1)")
    store.save_extraction({"id": "job", "imageId": "image", "status": "recognizing"}, "key")
    recovered = Store(tmp_path).extraction("job")
    assert recovered["status"] == "failed"
    assert "interrupted" in recovered["error"]


def test_single_worker_and_deletion_guard(tmp_path):
    entered = threading.Event()
    release = threading.Event()
    running = 0
    maximum = 0

    def slow(path):
        nonlocal running, maximum
        running += 1
        maximum = max(maximum, running)
        entered.set()
        assert release.wait(5)
        running -= 1
        return sample_blocks()

    with TestClient(create_app(tmp_path, recognizer=slow)) as client:
        image_id = upload(client)
        first = client.post("/v1/extractions", json={"imageId": image_id}).json()
        assert entered.wait(5)
        try:
            second = client.post("/v1/extractions", json={"imageId": image_id, "rotation": 90}).json()
            assert client.delete(f"/v1/images/{image_id}").status_code == 409
        finally:
            release.set()
        assert wait_for_job(client, first["id"])["status"] == "completed"
        assert wait_for_job(client, second["id"])["status"] == "completed"
        assert maximum == 1


def test_external_origins_and_traversal_are_rejected(client):
    assert client.get("/v1/library", headers={"Origin": "https://example.com"}).status_code == 403
    assert client.get("/v1/library", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/v1/images/not-a-real-id/preview").status_code == 404
    assert client.post("/v1/extractions", json={"imageId": "../../proposal.md"}).status_code == 404


def test_enrichment_cannot_overwrite_photo_definition(client, monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "test-local")
    image_id = upload(client)
    job = client.post("/v1/extractions", json={"imageId": image_id}).json()
    result = wait_for_job(client, job["id"])
    cards = result["draft_cards"]
    for card in cards:
        card.update(definition="", part_of_speech="", confirmed=True)
    response = client.post("/v1/cards/enrich", json={"extractionId": job["id"], "cards": cards})
    assert response.status_code == 400
    assert client.get("/v1/health").json()["metrics"]["modelCalls"] == 0


def test_enrichment_marks_generated_and_only_fills_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "test-local")
    calls = []

    def enrich(cards, fields_by_id):
        calls.extend(cards)
        assert fields_by_id[cards[0].id] == ["definition"]
        return [c.model_copy(update={
            "definition": "資源", "definitionOrigin": "model", "confirmed": False,
            "selected": False, "needs_review": True,
        }) for c in cards]

    monkeypatch.setattr("backend.model.enrich", enrich)
    with TestClient(create_app(tmp_path, recognizer=lambda path: [
        block("b1", "resource", 20, 20), block("b2", "n.", 160, 20),
    ])) as client:
        image_id = upload(client)
        job = client.post("/v1/extractions", json={"imageId": image_id}).json()
        result = wait_for_job(client, job["id"])
        cards = result["draft_cards"]
        cards[0]["confirmed"] = True
        response = client.post("/v1/cards/enrich", json={"extractionId": job["id"], "cards": cards})
        assert response.status_code == 200, response.text
        card = response.json()["cards"][0]
        assert card["definitionOrigin"] == "model" and not card["selected"] and not card["confirmed"]
        assert len(calls) == 1


@pytest.mark.parametrize("definition", ["手動校正的資源", ""])
def test_pos_only_enrichment_protects_original_definition(tmp_path, monkeypatch, definition):
    monkeypatch.setenv("OLLAMA_MODEL", "test-local")
    calls = []

    def enrich(cards, fields_by_id):
        calls.extend(cards)
        assert fields_by_id[cards[0].id] == ["part_of_speech"]
        assert cards[0].definition == definition
        return [c.model_copy(update={
            "part_of_speech": "n.", "partOfSpeechOrigin": "model",
            "confirmed": False, "selected": False, "needs_review": True,
        }) for c in cards]

    monkeypatch.setattr("backend.model.enrich", enrich)
    with TestClient(create_app(tmp_path, recognizer=lambda path: [
        block("b1", "resource", 20, 20), block("b2", "資源", 180, 20),
    ])) as client:
        image_id = upload(client)
        job = client.post("/v1/extractions", json={"imageId": image_id}).json()
        result = wait_for_job(client, job["id"])
        cards = result["draft_cards"]
        cards[0].update(definition=definition, definitionOrigin="manual")
        body = {"extractionId": job["id"], "cards": cards}
        assert client.post("/v1/cards/enrich", json=body).status_code == 400
        assert not calls
        cards[0]["confirmed"] = True
        response = client.post("/v1/cards/enrich", json=body)
        assert response.status_code == 200, response.text
        card = response.json()["cards"][0]
        assert card["part_of_speech"] == "n." and card["partOfSpeechOrigin"] == "model"
        assert card["definition"] == definition and card["definitionOrigin"] == "manual"
        assert not card["confirmed"] and not card["selected"] and card["needs_review"]
        saved = {"extractionId": job["id"], "cards": [card]}
        assert client.put(f"/v1/extractions/{job['id']}/cards", json=saved).status_code == 200
        restored = client.get(f"/v1/extractions/{job['id']}").json()["reviewed_cards"][0]
        assert restored["partOfSpeechOrigin"] == "model"
        assert len(calls) == 1


def test_model_configuration_is_local(monkeypatch):
    from backend.model import settings
    monkeypatch.setenv("OLLAMA_URL", "https://remote.example")
    with pytest.raises(ValueError, match="local"):
        settings()
