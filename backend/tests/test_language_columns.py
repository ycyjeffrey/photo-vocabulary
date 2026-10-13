import pytest
from PIL import Image

from backend.layout import detect_language_boundary, structure
from backend.ocr import recognize
from backend.schemas import Block


def block(id, text, x, y=30, width=50):
    return Block(id=id, text=text, bbox=(x, y, x + width, y + 30), ocr_score=0.98)


def test_language_gutter_is_not_a_second_word_list():
    pair = [block("a", "dog", 50), block("b", "狗", 520)]
    assert detect_language_boundary(pair) == 310
    double = pair + [block("c", "cat", 950), block("d", "貓", 1420)]
    assert detect_language_boundary(double) is None
    assert detect_language_boundary([block("a", "dog", 50)]) is None
    assert detect_language_boundary(pair + [block("c", "long term", 50, 100, 500)]) is None


@pytest.mark.parametrize("layout", ["auto", "single", "eng-zh"])
def test_each_language_gets_its_own_crop_and_global_coordinates(tmp_path, monkeypatch, layout):
    image = tmp_path / "bilingual.png"
    Image.new("RGB", (900, 200), "white").save(image)
    calls = []
    counted = []
    split = 450 if layout == "eng-zh" else 310

    def ocr(crop, *, lang, **kwargs):
        calls.append((lang, crop.size))
        entries = {
            "chi_tra+eng": [("dog", 50), ("狗", 520)],
            "eng": [("dog", 50)],
        }[lang]
        return {
            "text": [text for text, _ in entries], "conf": [98] * len(entries),
            "left": [x for _, x in entries], "top": [30] * len(entries),
            "width": [50] * len(entries), "height": [30] * len(entries),
        }

    monkeypatch.setattr("backend.ocr.pytesseract.image_to_data", ocr)
    def chinese(crop, offset_x, offset_y):
        calls.append(("paddleocr", crop.size))
        return [block("chinese", "狗", 520 - split + offset_x, 30 + offset_y).model_copy(
            update={"language": "chi_tra", "ocr_engine": "paddleocr"})]

    monkeypatch.setattr("backend.ocr.chinese_ocr.recognize", chinese)
    blocks = recognize(image, layout, lambda: counted.append(True))
    assert calls[-2:] == [("eng", (split, 200)), ("paddleocr", (900 - split, 200))]
    assert len(calls) == len(counted) == (2 if layout == "eng-zh" else 3)
    assert [b.bbox for b in blocks] == [(50, 30, 100, 60), (520, 30, 570, 60)]
    assert len({b.id for b in blocks}) == len(blocks)
    assert [b.language for b in blocks] == ["eng", "chi_tra"]
    assert [b.ocr_engine for b in blocks] == ["tesseract", "paddleocr"]
    cards, warnings = structure(blocks, 900, layout)
    assert [(c.term, c.definition) for c in cards] == [("dog", "狗")]
    assert not cards[0].confirmed
    assert not warnings


def test_bilingual_pairing_preserves_rows_phrases_pos_and_wrapped_meanings():
    blocks = [
        block("a", "look after", 50, width=150), block("pos", "V.", 250),
        block("b", "照顧；", 520), block("c", "照料", 520, 65),
        block("d", "dog", 50, 140), block("e", "狗", 520, 140),
        block("f", "cat", 50, 210),
    ]
    cards, warnings = structure(blocks, 900, "eng-zh")
    assert [(c.term, c.part_of_speech, c.definition) for c in cards] == [
        ("look after", "v.", "照顧；照料"), ("dog", "", "狗"), ("cat", "", ""),
    ]
    assert cards[0].source_block_ids == ["a", "pos", "b", "c"]
    assert cards[-1].needs_review and not cards[-1].selected
    assert not warnings


def test_chinese_bands_follow_english_rows_without_merging_cards(tmp_path, monkeypatch):
    path = tmp_path / "two-rows.png"
    Image.new("RGB", (900, 300), "white").save(path)
    bands = []
    calls = []

    def english(image, *, lang, **kwargs):
        assert lang == "eng"
        return {"text": ["dog", "cat"], "conf": [98, 98], "left": [50, 50],
                "top": [30, 180], "width": [50, 50], "height": [30, 30]}

    def chinese(image, offset_x, offset_y):
        bands.append((image.size, offset_x, offset_y))
        first = offset_y == 0
        return [block("meaning", "狗" if first else "貓", 520, 30 if first else 180).model_copy(
            update={"language": "chi_tra", "ocr_engine": "paddleocr"})]

    monkeypatch.setattr("backend.ocr.pytesseract.image_to_data", english)
    monkeypatch.setattr("backend.ocr.chinese_ocr.recognize", chinese)
    blocks = recognize(path, "eng-zh", lambda: calls.append(True))
    assert bands == [((450, 165), 450, 0), ((450, 135), 450, 165)]
    assert len(calls) == 3
    cards, warnings = structure(blocks, 900, "eng-zh")
    assert [(card.term, card.definition) for card in cards] == [("dog", "狗"), ("cat", "貓")]
    assert not warnings


def test_unrecognized_chinese_is_not_appended_to_the_english_word():
    cards, _ = structure([block("a", "dog", 50), block("b", "XX", 520)], 900, "eng-zh")
    assert cards[0].term == "dog"
    assert cards[0].definition == "XX"
    assert cards[0].needs_review and not cards[0].selected
    assert "no recognized Chinese" in cards[0].review_reason


@pytest.mark.parametrize("layout", ["auto", "single", "eng-zh"])
def test_language_roles_survive_chinese_model_returning_latin_text(layout):
    chinese = block("b", "XX", 520).model_copy(update={"language": "chi_tra"})
    cards, _ = structure([block("a", "dog", 50), chinese], 900, layout)
    assert [(c.term, c.definition) for c in cards] == [("dog", "XX")]
    assert cards[0].needs_review and not cards[0].selected


def test_uncertain_chinese_continuation_is_not_a_new_english_word():
    continuation = block("c", "XX", 520, 65).model_copy(update={"language": "chi_tra"})
    cards, _ = structure([block("a", "dog", 50), block("b", "狗", 520), continuation], 900, "auto")
    assert len(cards) == 1
    assert cards[0].term == "dog" and "c" in cards[0].source_block_ids
    assert cards[0].needs_review and not cards[0].selected


@pytest.mark.parametrize("layout", ["auto", "eng-zh"])
def test_printed_column_separator_is_not_part_of_the_word(layout):
    cards, _ = structure([
        block("a", "dog", 50), block("divider", "|", 449, width=2), block("b", "狗", 520),
    ], 900, layout)
    assert [(c.term, c.definition) for c in cards] == [("dog", "狗")]


def test_orphan_chinese_does_not_attach_to_a_distant_word():
    cards, warnings = structure([block("a", "dog", 50), block("b", "狗", 520, 180)], 900, "eng-zh")
    assert cards[0].definition == ""
    assert any("Unpaired definition" in warning for warning in warnings)
