import math
import os
import threading
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal

from PIL import Image

from .schemas import Block

ROOT = Path(__file__).resolve().parents[1]
Language = Literal["eng", "chi_tra"]
DETECTION_MODEL = "PP-OCRv5_server_det"
RECOGNITION_MODELS = {"eng": "en_PP-OCRv5_mobile_rec", "chi_tra": "PP-OCRv5_server_rec"}
MODELS = (DETECTION_MODEL, *RECOGNITION_MODELS.values())
MODEL_FILES = ("inference.json", "inference.pdiparams", "inference.yml")
_lock = threading.Lock()


def model_root() -> Path:
    return Path(os.environ.get("PADDLE_OCR_MODEL_DIR", str(ROOT / ".local" / "paddleocr")))


def readiness(language: Language | None = None) -> tuple[bool, str]:
    try:
        version("paddleocr")
        version("paddlepaddle")
    except PackageNotFoundError:
        return False, "PaddleOCR is not installed. Run scripts/setup.sh."
    models = MODELS if language is None else (DETECTION_MODEL, RECOGNITION_MODELS[language])
    missing = [f"{name}_infer/{file}" for name in models for file in MODEL_FILES
               if not (model_root() / f"{name}_infer" / file).is_file()]
    if missing:
        return False, "Local PaddleOCR models are missing. Run scripts/setup.sh."
    return True, "PaddleOCR dedicated English + Chinese models (local CPU) ready"


def model_signature() -> dict:
    packages = {}
    for name in ("paddleocr", "paddlepaddle", "paddlex"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return {
        "packages": packages,
        "files": [(str(path), path.stat().st_size, path.stat().st_mtime_ns)
                  for name in MODELS for file in MODEL_FILES
                  if (path := model_root() / f"{name}_infer" / file).is_file()],
    }


@lru_cache(maxsize=2)
def engine(language: Language):
    ready, message = readiness(language)
    if not ready:
        raise RuntimeError(message)
    # Explicit local paths and no model-source probes: inference must work offline.
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(model_root() / "cache"))
    from paddleocr import PaddleOCR

    return PaddleOCR(
        text_detection_model_name=DETECTION_MODEL,
        text_detection_model_dir=str(model_root() / f"{DETECTION_MODEL}_infer"),
        text_recognition_model_name=RECOGNITION_MODELS[language],
        text_recognition_model_dir=str(model_root() / f"{RECOGNITION_MODELS[language]}_infer"),
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        text_rec_score_thresh=0.0,
        device="cpu",
        enable_mkldnn=False,
        cpu_threads=4,
    )


def recognize(image: Image.Image, offset_x: int = 0, offset_y: int = 0,
              language: Language = "chi_tra") -> list[Block]:
    import numpy as np

    # PaddleOCR's array input is BGR. Disable geometric transforms to preserve boxes.
    bgr = np.asarray(image.convert("RGB"))[:, :, ::-1].copy()
    with _lock:
        results = list(engine(language).predict(bgr))
    if len(results) != 1:
        raise RuntimeError("PaddleOCR returned an unexpected number of images.")
    result = results[0]
    texts, scores, boxes = result["rec_texts"], result["rec_scores"], result["rec_boxes"]
    if not len(texts) == len(scores) == len(boxes):
        raise RuntimeError("PaddleOCR returned mismatched text, scores, and boxes.")
    blocks = []
    for text, score, box in zip(texts, scores, boxes):
        score = float(score)
        if not math.isfinite(score) or not 0 <= score <= 1 or len(box) != 4:
            raise RuntimeError("PaddleOCR returned invalid confidence or coordinates.")
        x1, y1, x2, y2 = (float(value) for value in box)
        if not all(math.isfinite(value) for value in (x1, y1, x2, y2)):
            raise RuntimeError("PaddleOCR returned non-finite coordinates.")
        x1, y1 = max(0, math.floor(x1)), max(0, math.floor(y1))
        x2, y2 = min(image.width, math.ceil(x2)), min(image.height, math.ceil(y2))
        if x2 <= x1 or y2 <= y1:
            raise RuntimeError("PaddleOCR returned an empty or out-of-bounds box.")
        if not text.strip():
            continue
        blocks.append(Block(
            id=f"b{len(blocks) + 1}", text=text.strip(),
            bbox=(x1 + offset_x, y1 + offset_y, x2 + offset_x, y2 + offset_y),
            ocr_score=score, language=language, ocr_engine="paddleocr",
        ))
    return blocks
