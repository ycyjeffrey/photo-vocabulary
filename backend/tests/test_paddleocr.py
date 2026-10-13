from types import SimpleNamespace
import os
import socket
import sys

import pytest
from PIL import Image

from backend import paddle_ocr
from scripts.generate_demo import generate


@pytest.mark.parametrize("language,text", [("eng", "dog"), ("chi_tra", "狗")])
def test_local_array_input_and_source_coordinates(monkeypatch, language, text):
    def predict(image):
        assert image.shape == (60, 100, 3)
        assert image[0, 0].tolist() == [0, 0, 255]
        return [{"rec_texts": [text], "rec_scores": [0.93], "rec_boxes": [[10.2, 5.1, 50.4, 30.6]]}]

    def engine(selected):
        assert selected == language
        return SimpleNamespace(predict=predict)

    monkeypatch.setattr(paddle_ocr, "engine", engine)
    blocks = paddle_ocr.recognize(Image.new("RGB", (100, 60), "red"), 450, 100, language)
    assert len(blocks) == 1
    assert blocks[0].bbox == (460, 105, 501, 131)
    assert blocks[0].text == text and blocks[0].ocr_score == 0.93
    assert blocks[0].language == language and blocks[0].ocr_engine == "paddleocr"
    assert blocks[0].original_text is None


@pytest.mark.parametrize("result", [
    [],
    [{"rec_texts": ["狗"], "rec_scores": [], "rec_boxes": []}],
    [{"rec_texts": ["狗"], "rec_scores": [float("nan")], "rec_boxes": [[1, 1, 5, 5]]}],
    [{"rec_texts": ["狗"], "rec_scores": [0.9], "rec_boxes": [[101, 1, 105, 5]]}],
])
def test_malformed_output_is_an_error_not_silent_success(monkeypatch, result):
    monkeypatch.setattr(paddle_ocr, "engine", lambda language: SimpleNamespace(predict=lambda image: result))
    with pytest.raises(RuntimeError, match="PaddleOCR"):
        paddle_ocr.recognize(Image.new("RGB", (100, 60)))


def test_inference_failure_is_not_replaced_with_tesseract(monkeypatch):
    def fail(image):
        raise RuntimeError("Paddle inference failed")

    monkeypatch.setattr(paddle_ocr, "engine", lambda language: SimpleNamespace(predict=fail))
    with pytest.raises(RuntimeError, match="Paddle inference failed"):
        paddle_ocr.recognize(Image.new("RGB", (100, 60)))


def test_missing_models_fail_before_loading_or_downloading(monkeypatch, tmp_path):
    monkeypatch.setenv("PADDLE_OCR_MODEL_DIR", str(tmp_path))
    ready, message = paddle_ocr.readiness()
    assert not ready and "scripts/setup.sh" in message
    with pytest.raises(RuntimeError, match="models are missing"):
        paddle_ocr.engine.__wrapped__("eng")


def test_model_signature_tracks_model_files(monkeypatch, tmp_path):
    monkeypatch.setenv("PADDLE_OCR_MODEL_DIR", str(tmp_path))
    for name in paddle_ocr.MODELS:
        directory = tmp_path / f"{name}_infer"
        directory.mkdir()
        for file in paddle_ocr.MODEL_FILES:
            (directory / file).write_bytes(b"test")
    assert paddle_ocr.readiness()[0]
    before = paddle_ocr.model_signature()
    (tmp_path / f"{paddle_ocr.RECOGNITION_MODELS['eng']}_infer" / "inference.pdiparams").write_bytes(b"updated")
    assert paddle_ocr.model_signature() != before


@pytest.mark.parametrize("language,model", [
    ("eng", "en_PP-OCRv5_mobile_rec"), ("chi_tra", "PP-OCRv5_server_rec"),
])
def test_each_language_loads_its_own_local_recognizer(monkeypatch, language, model):
    monkeypatch.setattr(paddle_ocr, "readiness", lambda language: (True, "ready"))
    monkeypatch.setitem(sys.modules, "paddleocr", SimpleNamespace(PaddleOCR=lambda **kwargs: kwargs))
    config = paddle_ocr.engine.__wrapped__(language)
    assert config["text_recognition_model_name"] == model
    assert config["text_recognition_model_dir"] == str(paddle_ocr.model_root() / f"{model}_infer")
    assert config["device"] == "cpu"
    assert config["use_doc_unwarping"] is False


@pytest.mark.skipif(os.environ.get("RUN_OCR_TESTS") != "1", reason="Set RUN_OCR_TESTS=1 for actual PaddleOCR")
@pytest.mark.parametrize("language,expected", [("eng", "dog"), ("chi_tra", "狗")])
def test_actual_inference_works_without_network(monkeypatch, tmp_path, language, expected):
    generate(tmp_path, os.environ.get("DEMO_FONT"))
    attempts = []

    def reject_network(sock, address):
        attempts.append(address)
        raise AssertionError("OCR must not make network connections")

    paddle_ocr.engine.cache_clear()
    monkeypatch.setattr(socket.socket, "connect", reject_network)
    with Image.open(tmp_path / "bilingual.png") as image:
        left, right = (0, 450) if language == "eng" else (450, 900)
        blocks = paddle_ocr.recognize(image.crop((left, 0, right, 170)), left, language=language)
    assert [b.text for b in blocks] == [expected]
    assert all(left <= b.bbox[0] < b.bbox[2] <= right for b in blocks)
    assert attempts == []
