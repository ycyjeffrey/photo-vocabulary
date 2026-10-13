import re
from statistics import median

from .schemas import Block, Card

HAN = re.compile(r"[\u3400-\u9fff]")
LATIN = re.compile(r"[A-Za-z]")
POS = re.compile(
    r"^(?:(?:n|v|vt|vi|adj|adv|prep|pron|conj|interj|art|aux|phr)\.)+$",
    re.I,
)
NUMBER = re.compile(r"^\d+[.)、]?$")
HEADINGS = {
    "vocabulary", "vocabulary list", "word list", "words", "unit", "lesson",
    "word", "meaning", "definition", "english", "chinese", "new words",
}


def visual_rows(blocks: list[Block]) -> list[list[Block]]:
    rows: list[list[Block]] = []
    for block in sorted(blocks, key=lambda b: ((b.bbox[1] + b.bbox[3]) / 2, b.bbox[0])):
        center = (block.bbox[1] + block.bbox[3]) / 2
        height = block.bbox[3] - block.bbox[1]
        if rows:
            previous = rows[-1]
            row_center = median((b.bbox[1] + b.bbox[3]) / 2 for b in previous)
            row_height = median(b.bbox[3] - b.bbox[1] for b in previous)
            if abs(center - row_center) <= max(height, row_height) * 0.55:
                previous.append(block)
                continue
        rows.append([block])
    return [sorted(row, key=lambda b: b.bbox[0]) for row in rows]


def join_text(blocks: list[Block]) -> str:
    text = " ".join(b.text.strip() for b in blocks)
    text = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff；，。、;,])", "", text)
    text = re.sub(r"(?<=[；，。、;,])\s+(?=[\u3400-\u9fff])", "", text)
    return text.strip()


def is_english_candidate(block: Block) -> bool:
    return bool(LATIN.search(block.text)) and not POS.fullmatch(block.text.strip())


def detect_boundary(blocks: list[Block], width: int) -> float | None:
    boundaries = []
    for row in visual_rows(blocks):
        seen_chinese = False
        for index, block in enumerate(row):
            if HAN.search(block.text):
                seen_chinese = True
            elif seen_chinese and is_english_candidate(block) and block.bbox[0] > width * 0.43:
                # A second vocabulary region needs its own following Chinese definition.
                if any(HAN.search(b.text) for b in row[index + 1:]):
                    previous = row[index - 1]
                    gap = block.bbox[0] - previous.bbox[2]
                    if gap > max(20, width * 0.025):
                        boundaries.append((previous.bbox[2] + block.bbox[0]) / 2)
                break
    return median(boundaries) if len(boundaries) >= 2 else None


def detect_language_boundary(blocks: list[Block]) -> int | None:
    """Find a shared gutter between English/POS and Chinese, not two word lists."""
    gutters = []
    for row in visual_rows(blocks):
        chinese_at = next((i for i, b in enumerate(row) if HAN.search(b.text)), None)
        if chinese_at is None or chinese_at == 0:
            continue
        left, right = row[:chinese_at], row[chinese_at:]
        if not any(is_english_candidate(b) for b in left):
            continue
        if any(is_english_candidate(b) for b in right):
            return None
        gutters.append((max(b.bbox[2] for b in left), min(b.bbox[0] for b in right)))
    if not gutters:
        return None
    left, right = max(g[0] for g in gutters), min(g[1] for g in gutters)
    if right - left < 12:
        return None
    split = round((left + right) / 2)
    if any(b.bbox[0] < split < b.bbox[2] for b in blocks):
        return None
    return split


def structure(blocks: list[Block], width: int, layout: str) -> tuple[list[Card], list[str]]:
    boundary = width / 2 if layout == "double" else (
        detect_boundary(blocks, width) if layout == "auto" else None
    )
    columns = [blocks] if boundary is None else [
        [b for b in blocks if (b.bbox[0] + b.bbox[2]) / 2 < boundary],
        [b for b in blocks if (b.bbox[0] + b.bbox[2]) / 2 >= boundary],
    ]
    cards: list[Card] = []
    warnings: list[str] = []
    for column in columns:
        language_boundary = width / 2 if layout == "eng-zh" else None
        previous: Card | None = None
        previous_bottom = 0
        definition_x = 0
        for row in visual_rows(column):
            content = [b for b in row if not NUMBER.fullmatch(b.text.strip())
                       and b.text.strip() not in {"|", "｜"}]
            if not content:
                continue
            chinese_at = next((i for i, b in enumerate(content) if (
                (b.bbox[0] + b.bbox[2]) / 2 >= language_boundary
                if language_boundary is not None else b.language == "chi_tra" or HAN.search(b.text)
            )), None)
            pos_at = next((i for i, b in enumerate(content) if POS.fullmatch(b.text.strip())
                           and (chinese_at is None or i < chinese_at)), None)
            stop = min(i for i in (chinese_at, pos_at, len(content)) if i is not None)
            term_blocks = content[:stop]
            term = join_text(term_blocks)
            term = re.sub(r"^\d+[.)、]?\s*", "", term).strip()
            height = max(b.bbox[3] - b.bbox[1] for b in row)
            top = min(b.bbox[1] for b in row)
            bottom = max(b.bbox[3] for b in row)
            if not term and chinese_at == 0:
                if (previous and top - previous_bottom <= height * 1.8
                        and content[0].bbox[0] >= definition_x - height):
                    previous.definition += join_text(content)
                    previous.source_block_ids.extend(b.id for b in content)
                    if any(b.ocr_score < 0.7 for b in content):
                        previous.needs_review = True
                        previous.selected = False
                        previous.review_reason = "; ".join(filter(None, [
                            previous.review_reason, "Low OCR score in wrapped definition; check the photo",
                        ]))
                    if any(is_english_candidate(b) or b.original_text is not None for b in content):
                        previous.needs_review = True
                        previous.selected = False
                        previous.review_reason = "; ".join(filter(None, [
                            previous.review_reason, "Uncertain OCR in wrapped definition; check the photo",
                        ]))
                    previous_bottom = bottom
                else:
                    warnings.append(f"Unpaired definition: {join_text(content)}")
                continue
            if (not LATIN.search(term) or term.lower() in HEADINGS
                    or re.match(r"^(unit|lesson|chapter)\s+\d+", term, re.I)):
                continue
            if len(term.split()) > 6 or re.search(r"[.!?。！？]$", term):
                if previous and top - previous_bottom <= height * 1.8:
                    previous.example = (previous.example + " " + join_text(content)).strip()
                    previous.source_block_ids.extend(b.id for b in content)
                    previous_bottom = bottom
                continue
            definition_blocks = content[chinese_at:] if chinese_at is not None else []
            definition = join_text(definition_blocks)
            pos_blocks = [content[pos_at]] if pos_at is not None else []
            reasons = []
            if not definition:
                reasons.append("Missing Chinese definition")
            elif not HAN.search(definition):
                reasons.append("Chinese column contains no recognized Chinese; check the photo")
            if pos_at is not None and pos_at + 1 < (chinese_at if chinese_at is not None else len(content)):
                reasons.append("Unpaired text after part of speech; check OCR")
            if any(b.ocr_score < 0.7 for b in content):
                reasons.append("Low OCR score; check the photo")
            if any(b.original_text is not None for b in content):
                reasons.append("Chinese-only OCR recheck changed the reading; verify the photo")
            if boundary is not None and any(b.bbox[0] < boundary < b.bbox[2] for b in content):
                reasons.append("Source crosses the column boundary")
            if language_boundary is not None and any(
                    b.bbox[0] < language_boundary < b.bbox[2] for b in content):
                reasons.append("Source crosses the English/Chinese boundary")
            if chinese_at is not None and any(is_english_candidate(b) for b in definition_blocks):
                reasons.append("Mixed-language definition or possible column mismatch")
            card = Card(
                id=f"card-{len(cards) + 1}", term=term,
                part_of_speech=join_text(pos_blocks).lower(),
                definition=definition, source_block_ids=[b.id for b in content],
                definitionOrigin="photo" if definition else "missing",
                partOfSpeechOrigin="photo" if pos_blocks else "missing",
                needs_review=bool(reasons), review_reason="; ".join(reasons) or None,
                selected=not reasons,
            )
            cards.append(card)
            previous = card
            previous_bottom = bottom
            definition_x = definition_blocks[0].bbox[0] if definition_blocks else content[-1].bbox[2]
    used = {source for card in cards for source in card.source_block_ids}
    unused = [b for b in blocks if is_english_candidate(b) and b.id not in used]
    warnings.extend(f"Possible missed text [{b.id}]: {b.text}" for b in unused)
    if not cards:
        warnings.append("No vocabulary rows found. Try a tighter crop or a different layout.")
    return cards, warnings
