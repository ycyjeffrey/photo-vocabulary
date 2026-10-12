import os

import pytest

from backend.layout import structure
from backend.ocr import readiness, recognize
from scripts.generate_demo import generate


@pytest.mark.skipif(os.environ.get("RUN_OCR_TESTS") != "1", reason="Set RUN_OCR_TESTS=1 for actual Tesseract tests")
def test_three_controlled_bilingual_samples(tmp_path):
    ready, reason = readiness()
    assert ready, reason
    expected = generate(tmp_path, os.environ.get("DEMO_FONT"))
    for name, width in [("single", 900), ("double", 1800), ("wrapped", 900)]:
        blocks = recognize(tmp_path / f"{name}.png")
        assert blocks and all(b.bbox[2] > b.bbox[0] and b.bbox[3] > b.bbox[1] for b in blocks)
        cards, warnings = structure(blocks, width, "auto")
        # Tesseract normalizes full-width semicolons to ASCII. Ignore only that
        # typographic width here; every term, POS, and Chinese character must match.
        actual = [{"term": c.term, "part_of_speech": c.part_of_speech,
                   "definition": c.definition.replace(";", "；")} for c in cards]
        assert actual == expected[name], {
            "sample": name, "cards": actual, "warnings": warnings,
            "blocks": [b.model_dump() for b in blocks],
        }
        if name == "wrapped":
            assert cards[-1].needs_review and not cards[-1].selected
