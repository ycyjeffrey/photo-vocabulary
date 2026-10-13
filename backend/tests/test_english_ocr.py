import os

import pytest
import pytesseract

from backend.layout import join_text, visual_rows
from backend.ocr import configuration
from backend.paddle_ocr import recognize
from scripts.generate_demo import ENGLISH_TERMS, english_sample


@pytest.mark.skipif(os.environ.get("RUN_OCR_TESTS") != "1", reason="Set RUN_OCR_TESTS=1 for actual English OCR")
@pytest.mark.parametrize("size,blur,angle", [
    (42, 0, 0), (18, 0.6, 4), (14, 0.5, 0), (18, 1.0, 0), (24, 0.5, 8),
])
def test_english_accuracy_preserves_spelling_phrases_and_punctuation(size, blur, angle):
    image = english_sample(os.environ.get("DEMO_FONT"), size, blur, angle)
    baseline = [line.strip() for line in pytesseract.image_to_string(
        image, lang="eng", config=f"{configuration()} --psm 6",
    ).splitlines() if line.strip()]
    blocks = recognize(image, language="eng")
    actual = [join_text(row) for row in visual_rows(blocks)]
    assert actual == ENGLISH_TERMS, {"actual": actual, "tesseract": baseline}
    assert all(b.language == "eng" and b.ocr_engine == "paddleocr" for b in blocks)
    assert all(0 <= b.bbox[0] < b.bbox[2] <= image.width
               and 0 <= b.bbox[1] < b.bbox[3] <= image.height for b in blocks)
