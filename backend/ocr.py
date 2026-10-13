import os
from collections.abc import Callable
from pathlib import Path

import pytesseract
from PIL import Image
from pytesseract import Output

from .schemas import Block
from . import paddle_ocr
from .layout import HAN, POS, detect_boundary, detect_language_boundary, join_text, visual_rows

ROOT = Path(__file__).resolve().parents[1]


def configuration() -> str:
    path = os.environ.get("TESSDATA_DIR", str(ROOT / ".local" / "tessdata"))
    return f'--tessdata-dir "{path}"' if Path(path).is_dir() else ""


def model_signature() -> dict:
    path = Path(os.environ.get("TESSDATA_DIR", str(ROOT / ".local" / "tessdata")))
    tesseract = [
        (language, file.stat().st_size, file.stat().st_mtime_ns)
        for language in ("eng", "chi_tra")
        if (file := path / f"{language}.traineddata").is_file()
    ]
    return {"layout_probe": tesseract, "recognition": paddle_ocr.model_signature()}


def readiness() -> tuple[bool, str]:
    try:
        languages = pytesseract.get_languages(config=configuration())
        missing = {"eng", "chi_tra"} - set(languages)
        if missing:
            return False, "Missing OCR languages: " + ", ".join(sorted(missing)) + ". Run scripts/setup.sh."
        ready, message = paddle_ocr.readiness()
        if not ready:
            return False, message
        return True, "PaddleOCR: dedicated English + Chinese models (local CPU); Tesseract layout probe"
    except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError, OSError) as exc:
        return False, f"Tesseract is unavailable: {exc}"


def recognize(path: Path, layout: str = "auto", on_call: Callable[[], None] | None = None) -> list[Block]:
    def region(image: Image.Image, offset: int = 0, offset_y: int = 0,
               language: str = "chi_tra+eng") -> list[Block]:
        if on_call:
            on_call()
        if language in {"eng", "chi_tra"}:
            return paddle_ocr.recognize(image, offset, offset_y, language=language)
        data = pytesseract.image_to_data(
            image, lang=language, config=f"{configuration()} --psm 6",
            output_type=Output.DICT, timeout=90,
        )
        blocks = []
        for index, text in enumerate(data["text"]):
            score = float(data["conf"][index])
            if not text.strip() or score < 0:
                continue
            x, y = data["left"][index] + offset, data["top"][index] + offset_y
            blocks.append(Block(
                id=f"b{len(blocks) + 1}", text=text.strip(),
                bbox=(x, y, x + data["width"][index], y + data["height"][index]),
                ocr_score=min(1, max(0, score / 100)),
                language=language,
            ))
        return blocks

    def paired_columns(image: Image.Image, split: int, offset: int = 0) -> list[Block]:
        english = region(image.crop((0, 0, split, image.height)), offset, language="eng")
        rows = visual_rows(english)
        # Single-character meanings stacked vertically look like vertical writing to
        # PaddleOCR. English row anchors keep separate cards from becoming one line.
        cuts = [0]
        for previous, row in zip(rows, rows[1:]):
            top = min(b.bbox[1] for b in row)
            height = max(b.bbox[3] - b.bbox[1] for b in row)
            previous_bottom = max(b.bbox[3] for b in previous)
            cuts.append(max(previous_bottom, round(top - height / 2)))
        cuts.append(image.height)
        blocks = list(english)
        for top, bottom in zip(cuts, cuts[1:]):
            blocks += region(image.crop((split, top, image.width, bottom)),
                             split + offset, top, language="chi_tra")
        return blocks

    def vocabulary_region(image: Image.Image, offset: int = 0,
                          initial: list[Block] | None = None) -> list[Block]:
        initial = region(image, offset) if initial is None else initial
        boundary = detect_language_boundary(initial)
        if boundary is None:
            if any(HAN.search(b.text) for b in initial):
                raise RuntimeError(
                    "無法可靠分隔英中欄位。請選擇「左英文｜右中文」，"
                    "並裁切到分隔線位於圖片中央後重試。"
                )
            return region(image, offset, language="eng")
        split = boundary - offset
        return paired_columns(image, split, offset)

    with Image.open(path) as image:
        initial = [] if layout in {"double", "eng-zh"} else region(image)
        boundary = image.width / 2 if layout == "double" else (
            detect_boundary(initial, image.width) if layout == "auto" else None
        )
        if layout == "eng-zh":
            split = image.width // 2
            blocks = paired_columns(image, split)
        elif boundary is None:
            blocks = vocabulary_region(image, initial=initial)
        else:
            split = round(boundary)
            blocks = vocabulary_region(image.crop((0, 0, split, image.height)))
            blocks += vocabulary_region(image.crop((split, 0, image.width, image.height)), split)
        # English models sometimes interpret Chinese strokes as Latin letters. Recheck
        # only suspect definition regions, retaining the original reading for review.
        column_blocks = [blocks] if boundary is None else [
            [b for b in blocks if (b.bbox[0] + b.bbox[2]) / 2 < boundary],
            [b for b in blocks if (b.bbox[0] + b.bbox[2]) / 2 >= boundary],
        ]
        rechecks = 0
        for column in column_blocks:
            for row in visual_rows(column):
                pos_index = next((i for i, b in enumerate(row) if POS.fullmatch(b.text)), None)
                if pos_index is None:
                    continue
                candidates = row[pos_index + 1:]
                if (not candidates or rechecks >= 20 or any(HAN.search(b.text) for b in candidates)
                        or all(b.ocr_score >= 0.75 for b in candidates)):
                    continue
                box = (
                    max(0, min(b.bbox[0] for b in candidates) - 8),
                    max(0, min(b.bbox[1] for b in candidates) - 8),
                    min(image.width, max(b.bbox[2] for b in candidates) + 8),
                    min(image.height, max(b.bbox[3] for b in candidates) + 8),
                )
                rechecks += 1
                revised = region(image.crop(box), box[0], box[1], "chi_tra")
                if revised and any(HAN.search(b.text) for b in revised):
                    original = join_text(candidates)
                    for block in revised:
                        block.original_text = original
                    blocks = [b for b in blocks if b not in candidates] + revised
        for index, block in enumerate(blocks):
            block.id = f"b{index + 1}"
        return blocks
