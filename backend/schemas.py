from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Crop(StrictModel):
    x: float = Field(ge=0, lt=1)
    y: float = Field(ge=0, lt=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def within_image(self):
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("Crop must stay inside the rotated image.")
        return self


class ExtractionRequest(StrictModel):
    imageId: str
    rotation: Literal[0, 90, 180, 270] = 0
    crop: Crop | None = None
    layout: Literal["auto", "single", "double"] = "auto"


class Block(StrictModel):
    id: str
    text: str
    bbox: tuple[int, int, int, int]
    ocr_score: float = Field(ge=0, le=1)
    original_text: str | None = None


class Card(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    term: str = Field(max_length=300)
    part_of_speech: str = Field(default="", max_length=100)
    definition: str = Field(default="", max_length=3000)
    example: str = Field(default="", max_length=3000)
    source_block_ids: list[str] = Field(default_factory=list, max_length=500)
    definitionOrigin: Literal["photo", "model", "manual", "missing"] = "photo"
    partOfSpeechOrigin: Literal["photo", "model", "manual", "missing"] = "photo"
    needs_review: bool = False
    review_reason: str | None = None
    selected: bool = False
    confirmed: bool = False


class CardRequest(StrictModel):
    extractionId: str
    cards: list[Card] = Field(max_length=500)


class EnrichRequest(CardRequest):
    pass
