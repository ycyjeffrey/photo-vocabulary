import hashlib
import io
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .schemas import ExtractionRequest

MAX_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 24_000_000
MAX_SIDE = 3200
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def decode_image(data: bytes) -> Image.Image:
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Please upload a JPG or PNG no larger than 15 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {"JPEG", "PNG"}:
                    raise ValueError("Only JPEG and PNG images are supported.")
                if image.width * image.height > MAX_PIXELS:
                    raise ValueError("Decoded image exceeds the 24-megapixel limit.")
                image.load()
                oriented = ImageOps.exif_transpose(image)
                if oriented.mode in {"RGBA", "LA", "P"}:
                    rgba = oriented.convert("RGBA")
                    background = Image.new("RGBA", rgba.size, "white")
                    return Image.alpha_composite(background, rgba).convert("RGB")
                return oriented.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ValueError("Invalid, damaged, or oversized image.") from exc


def image_hash(image: Image.Image) -> str:
    return hashlib.sha256(
        f"{image.width}x{image.height}:RGB:".encode() + image.tobytes()
    ).hexdigest()


def preprocess(path: Path, output: Path, request: ExtractionRequest) -> dict:
    with Image.open(path) as original:
        image = original.convert("RGB")
    original_size = image.size
    if request.rotation:
        image = image.rotate(-request.rotation, expand=True)
    rotated_size = image.size
    box = (0, 0, image.width, image.height)
    if request.crop:
        crop = request.crop
        box = (
            round(crop.x * image.width), round(crop.y * image.height),
            round((crop.x + crop.width) * image.width),
            round((crop.y + crop.height) * image.height),
        )
        if box[2] - box[0] < 20 or box[3] - box[1] < 20:
            raise ValueError("Crop must be at least 20 × 20 pixels.")
        image = image.crop(box)
    crop_size = image.size
    image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    image.save(output, "PNG")
    return {
        "originalSize": original_size,
        "rotation": request.rotation,
        "rotatedSize": rotated_size,
        "cropBox": box,
        "processedSize": image.size,
        "scale": [image.width / crop_size[0], image.height / crop_size[1]],
        "coordinateSpace": "processed-image",
    }
