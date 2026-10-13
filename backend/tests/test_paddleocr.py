from types import SimpleNamespace
import os
import socket

import pytest
from PIL import Image

from backend import chinese_ocr
from scripts.generate_demo import generate


def test_local_array_input_and_source_coordinates(monkeypatch):
    def predict(image):
        assert image.shape == (60, 100, 3)
        assert image[0, 0].tolist() == [0, 0, 255]
        return [{"rec_texts": ["狗"], "rec_scores": [0.93], "rec_boxes": [[10.2, 5.1, 50.4, 30.6]]}]

    monkeypatch.setattr(chinese_ocr, "engine", lambda: SimpleNamespace(predict=predict))
    blocks = chinese_ocr.recognize(Image.new("RGB", (100, 60), "red"), 450, 100)
    assert len(blocks) == 1
    assert blocks[0].bbox == (460, 105, 501, 131)
    assert blocks[0].text == "狗" and blocks[0].ocr_score == 0.93
    assert blocks[0].language == "chi_tra" and blocks[0].ocr_engine == "paddleocr"
    assert blocks[0].original_text is None


@pytest.mark.parametrize("result", [
    [],
    [{"rec_texts": ["狗"], "rec_scores": [], "rec_boxes": []}],
    [{"rec_texts": ["狗"], "rec_scores": [float("nan")], "rec_boxes": [[1, 1, 5, 5]]}],
    [{"rec_texts": ["狗"], "rec_scores": [0.9], "rec_boxes": [[101, 1, 105, 5]]}],
])
def test_malformed_output_is_an_error_not_silent_success(monkeypatch, result):
    monkeypatch.setattr(chinese_ocr, "engine", lambda: SimpleNamespace(predict=lambda image: result))
    with pytest.raises(RuntimeError, match="Chinese OCR"):
        chinese_ocr.recognize(Image.new("RGB", (100, 60)))


def test_inference_failure_is_not_replaced_with_tesseract(monkeypatch):
    def fail(image):
        raise RuntimeError("Paddle inference failed")

    monkeypatch.setattr(chinese_ocr, "engine", lambda: SimpleNamespace(predict=fail))
    with pytest.raises(RuntimeError, match="Paddle inference failed"):
        chinese_ocr.recognize(Image.new("RGB", (100, 60)))


def test_missing_models_fail_before_loading_or_downloading(monkeypatch, tmp_path):
    monkeypatch.setenv("PADDLE_OCR_MODEL_DIR", str(tmp_path))
    ready, message = chinese_ocr.readiness()
    assert not ready and "scripts/setup.sh" in message
    with pytest.raises(RuntimeError, match="models are missing"):
        chinese_ocr.engine.__wrapped__()


def test_model_signature_tracks_model_files(monkeypatch, tmp_path):
    monkeypatch.setenv("PADDLE_OCR_MODEL_DIR", str(tmp_path))
    for name in chinese_ocr.MODELS:
        directory = tmp_path / f"{name}_infer"
        directory.mkdir()
        for file in chinese_ocr.MODEL_FILES:
            (directory / file).write_bytes(b"test")
    assert chinese_ocr.readiness()[0]
    before = chinese_ocr.model_signature()
    (tmp_path / f"{chinese_ocr.MODELS[0]}_infer" / "inference.pdiparams").write_bytes(b"updated")
    assert chinese_ocr.model_signature() != before


@pytest.mark.skipif(os.environ.get("RUN_OCR_TESTS") != "1", reason="Set RUN_OCR_TESTS=1 for actual PaddleOCR")
def test_actual_chinese_inference_works_without_network(monkeypatch, tmp_path):
    generate(tmp_path, os.environ.get("DEMO_FONT"))
    attempts = []

    def reject_network(sock, address):
        attempts.append(address)
        raise AssertionError("OCR must not make network connections")

    chinese_ocr.engine.cache_clear()
    monkeypatch.setattr(socket.socket, "connect", reject_network)
    with Image.open(tmp_path / "bilingual.png") as image:
        blocks = chinese_ocr.recognize(image.crop((450, 0, 900, 170)), 450)
    assert [b.text for b in blocks] == ["狗"]
    assert all(450 <= b.bbox[0] < b.bbox[2] <= 900 for b in blocks)
    assert attempts == []
