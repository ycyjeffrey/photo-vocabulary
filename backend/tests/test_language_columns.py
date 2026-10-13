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
        assert lang == "chi_tra+eng"
        calls.append((lang, crop.size))
        entries = [("dog", 50), ("狗", 520)]
        return {
            "text": [text for text, _ in entries], "conf": [98] * len(entries),
            "left": [x for _, x in entries], "top": [30] * len(entries),
            "width": [50] * len(entries), "height": [30] * len(entries),
        }

    monkeypatch.setattr("backend.ocr.pytesseract.image_to_data", ocr)
    def paddle(crop, offset_x, offset_y, *, language):
        calls.append((language, crop.size))
        text, x = ("dog", 50 + offset_x) if language == "eng" else ("狗", 520 - split + offset_x)
        return [block("word", text, x, 30 + offset_y).model_copy(
            update={"language": language, "ocr_engine": "paddleocr"})]

    monkeypatch.setattr("backend.ocr.paddle_ocr.recognize", paddle)
    blocks = recognize(image, layout, lambda: counted.append(True))
    assert calls[-2:] == [("eng", (split, 200)), ("chi_tra", (900 - split, 200))]
    assert len(calls) == len(counted) == (2 if layout == "eng-zh" else 3)
    assert [b.bbox for b in blocks] == [(50, 30, 100, 60), (520, 30, 570, 60)]
    assert len({b.id for b in blocks}) == len(blocks)
    assert [b.language for b in blocks] == ["eng", "chi_tra"]
    assert all(b.ocr_engine == "paddleocr" for b in blocks)
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

    def paddle(image, offset_x, offset_y, *, language):
        if language == "eng":
            return [block("dog", "dog", 50, 30), block("cat", "cat", 50, 180)]
        bands.append((image.size, offset_x, offset_y))
        first = offset_y == 0
        return [block("meaning", "狗" if first else "貓", 520, 30 if first else 180).model_copy(
            update={"language": "chi_tra", "ocr_engine": "paddleocr"})]

    monkeypatch.setattr("backend.ocr.paddle_ocr.recognize", paddle)
    blocks = recognize(path, "eng-zh", lambda: calls.append(True))
    assert bands == [((450, 165), 450, 0), ((450, 135), 450, 165)]
    assert len(calls) == 3
    cards, warnings = structure(blocks, 900, "eng-zh")
    assert [(card.term, card.definition) for card in cards] == [("dog", "狗"), ("cat", "貓")]
    assert not warnings


@pytest.mark.parametrize("text,term,pos", [
    ("look after v.", "look after", "v."),
    ("well-being n.", "well-being", "n."),
    ("don't v.", "don't", "v."),
    ("O'Brien", "O'Brien", ""),
])
def test_english_line_preserves_phrases_and_extracts_embedded_pos(text, term, pos):
    cards, warnings = structure([block("a", text, 30, width=300), block("b", "釋義", 520)], 900, "eng-zh")
    assert [(c.term, c.part_of_speech, c.definition) for c in cards] == [(term, pos, "釋義")]
    assert cards[0].source_block_ids == ["a", "b"]
    assert cards[0].partOfSpeechOrigin == ("photo" if pos else "missing")
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


@pytest.mark.parametrize("ambiguous", [False, True])
def test_layout_probe_is_never_used_as_final_english(tmp_path, monkeypatch, ambiguous):
    path = tmp_path / "probe.png"
    Image.new("RGB", (900, 200), "white").save(path)
    entries = [("d0g", 50, 30, 50)]
    if ambiguous:
        entries += [("狗", 520, 30, 50), ("long text", 50, 100, 530)]

    def probe(*args, **kwargs):
        assert kwargs["lang"] == "chi_tra+eng"
        return {"text": [b[0] for b in entries], "left": [b[1] for b in entries],
                "top": [b[2] for b in entries], "width": [b[3] for b in entries],
                "height": [30] * len(entries), "conf": [98] * len(entries)}

    def english(image, offset_x, offset_y, *, language):
        assert not ambiguous and language == "eng"
        return [block("english", "dog", 50).model_copy(
            update={"language": "eng", "ocr_engine": "paddleocr"})]

    monkeypatch.setattr("backend.ocr.pytesseract.image_to_data", probe)
    monkeypatch.setattr("backend.ocr.paddle_ocr.recognize", english)
    if ambiguous:
        with pytest.raises(RuntimeError, match="左英文｜右中文"):
            recognize(path, "auto")
    else:
        blocks = recognize(path, "auto")
        assert [b.text for b in blocks] == ["dog"]
        assert all(b.ocr_engine == "paddleocr" for b in blocks)
