import re
from collections import Counter

from .layout import is_english_candidate, join_text
from .schemas import Block, Card


def clean_field(value: str) -> str:
    return re.sub(r"[\t\r\n]+", " ", value).strip()


def validate_cards(cards: list[Card], extraction: dict) -> dict:
    blocks = {b["id"]: Block.model_validate(b) for b in extraction["ocr_blocks"]}
    originals = {card["id"]: card for card in extraction["draft_cards"]}
    id_counts = Counter(card.id for card in cards)
    source_counts = Counter(
        source for card in cards for source in set(card.source_block_ids)
        if source in blocks and is_english_candidate(blocks[source])
    )
    issues = []
    lines = []
    selected_count = 0
    for card in cards:
        errors = []
        notes = []
        unknown = set(card.source_block_ids) - blocks.keys()
        if id_counts[card.id] > 1:
            errors.append("Duplicate card ID")
        if unknown:
            errors.append("Unknown source block IDs")
        if len(set(card.source_block_ids)) != len(card.source_block_ids):
            errors.append("Repeated source block IDs")
        if not clean_field(card.term):
            errors.append("Term is required")
        if not clean_field(card.definition):
            errors.append("Definition is required")
        source_blocks = [blocks[s] for s in card.source_block_ids if s in blocks]
        english_sources = [b for b in source_blocks if is_english_candidate(b)]
        original = originals.get(card.id)
        if (original is not None or card.source_block_ids) and not english_sources:
            errors.append("Extracted cards need an English source block")
        if any(source_counts[b.id] > 1 for b in english_sources):
            notes.append("Source word is used by more than one card")
        if original:
            if card.term != original["term"]:
                notes.append("Spelling differs from the extracted source")
            if set(card.source_block_ids) != set(original["source_block_ids"]):
                notes.append("Source pairing differs from extraction")
            if original["needs_review"]:
                notes.append(original["review_reason"] or "Source needs review")
        elif english_sources and clean_field(card.term) not in join_text(english_sources):
            notes.append("Term differs from source text")
        if card.definitionOrigin == "model":
            notes.append("Generated definition must be checked")
        if card.partOfSpeechOrigin == "model":
            notes.append("Generated part of speech must be checked")
        if card.needs_review:
            notes.append(card.review_reason or "Card needs review")
        if card.selected:
            selected_count += 1
            if not card.confirmed:
                errors.append("Confirm this card against the photo before export")
            if not errors:
                lines.append(
                    clean_field(card.term) + "\t"
                    + clean_field(f"{card.part_of_speech} {card.definition}")
                )
        if errors or notes:
            issues.append({"cardId": card.id, "errors": errors, "warnings": list(dict.fromkeys(notes)),
                           "blocking": card.selected and bool(errors)})
    valid = selected_count > 0 and not any(issue["blocking"] for issue in issues)
    used = {s for card in cards for s in card.source_block_ids}
    missed = [b.id for b in blocks.values() if is_english_candidate(b) and b.id not in used]
    return {
        "valid": valid, "issues": issues, "missedBlockIds": missed,
        "selectedCount": selected_count, "tsv": "\n".join(lines) if valid else "",
    }
