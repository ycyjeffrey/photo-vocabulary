"""Generate original, controlled samples; these are NOT real textbook photographs."""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = [
    ("conserve", "v.", "節省；保護"),
    ("habitat", "n.", "棲息地"),
    ("resource", "n.", "資源"),
]
RIGHT = [
    ("protect", "v.", "保護"),
    ("nature", "n.", "自然"),
    ("forest", "n.", "森林"),
]
ENGLISH_TERMS = [
    "accommodation", "environment", "through", "thought", "thorough", "affect",
    "effect", "look after", "well-being", "don't", "O'Brien", "co-operate",
]


def fonts(font_path: str | None = None):
    candidates = [
        font_path,
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        "C:/Windows/Fonts/msjh.ttc",
    ]
    chinese = next((path for path in candidates if path and Path(path).is_file()), None)
    if not chinese:
        raise RuntimeError("Pass --font /path/to/a/Traditional-Chinese-font.ttf (or .ttc).")
    english_path = "/System/Library/Fonts/Supplemental/Arial.ttf"
    english = english_path if Path(english_path).is_file() else chinese
    return ImageFont.truetype(english, 42), ImageFont.truetype(chinese, 42)


def generate(output: Path, font_path: str | None = None):
    output.mkdir(parents=True, exist_ok=True)
    english, chinese = fonts(font_path)

    def row(draw, x, y, entry):
        term, pos, definition = entry
        draw.text((x, y), term, font=english, fill="#202020")
        draw.text((x + 270, y), pos, font=english, fill="#202020")
        draw.text((x + 345, y - 3), definition, font=chinese, fill="#202020")

    single = Image.new("RGB", (900, 410), "white")
    draw = ImageDraw.Draw(single)
    for index, entry in enumerate(SAMPLES):
        row(draw, 65, 65 + index * 100, entry)
    single.save(output / "single.png")

    double = Image.new("RGB", (1800, 410), "white")
    draw = ImageDraw.Draw(double)
    for index, (left, right) in enumerate(zip(SAMPLES, RIGHT)):
        row(draw, 65, 65 + index * 100, left)
        row(draw, 970, 65 + index * 100, right)
    double.save(output / "double.png")

    wrapped = Image.new("RGB", (900, 530), "white")
    draw = ImageDraw.Draw(wrapped)
    row(draw, 65, 60, ("conserve", "v.", "節省；"))
    draw.text((410, 115), "保護", font=chinese, fill="#202020")
    row(draw, 65, 230, SAMPLES[1])
    row(draw, 65, 370, ("resource", "n.", ""))
    wrapped.save(output / "wrapped.png")

    bilingual_entries = [("dog", "", "狗"), ("cat", "", "貓"), ("bird", "", "鳥")]
    bilingual = Image.new("RGB", (900, 410), "white")
    draw = ImageDraw.Draw(bilingual)
    for index, (term, _, definition) in enumerate(bilingual_entries):
        draw.text((65, 65 + index * 100), term, font=english, fill="#202020")
        draw.text((520, 62 + index * 100), definition, font=chinese, fill="#202020")
    bilingual.save(output / "bilingual.png")

    expected = {
        "notice": "Generated controlled samples, not real photos. No textbook content copied.",
        "single": [dict(zip(("term", "part_of_speech", "definition"), entry)) for entry in SAMPLES],
        "double": [dict(zip(("term", "part_of_speech", "definition"), entry)) for entry in SAMPLES + RIGHT],
        "bilingual": [dict(zip(("term", "part_of_speech", "definition"), entry)) for entry in bilingual_entries],
        "wrapped": [dict(zip(("term", "part_of_speech", "definition"), entry))
                    for entry in [SAMPLES[0], SAMPLES[1], ("resource", "n.", "")]],
    }
    (output / "expected.json").write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8")
    return expected


def english_sample(font_path: str | None = None, size: int = 24,
                   blur: float = 0.5, angle: float = 8) -> Image.Image:
    font = fonts(font_path)[0].font_variant(size=size)
    image = Image.new("RGB", (500, 65 * len(ENGLISH_TERMS) + 40), "white")
    draw = ImageDraw.Draw(image)
    for index, term in enumerate(ENGLISH_TERMS):
        draw.text((60, 20 + index * 65), term, font=font, fill="#606060")
    return image.filter(ImageFilter.GaussianBlur(blur)).rotate(
        angle, expand=True, fillcolor="white", resample=Image.Resampling.BICUBIC,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".local" / "demo")
    parser.add_argument("--font")
    args = parser.parse_args()
    generate(args.output, args.font)
    print(f"Created four controlled samples and ground truth in {args.output}")
