"""Download pinned official PaddleOCR weights; inference itself never downloads."""
import hashlib
import os
import shutil
import tarfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0"
MODELS = {
    "PP-OCRv5_server_det": "22a33e0ba6a21425ea4192da03bf4395c9a0c67902bd924b7328fc859073045d",
    "PP-OCRv5_server_rec": "d99be2ffd348943ab52876179168be4fb5b14f5f0812f2ae4c76d89ec2ea750a",
}


def digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def install():
    root = Path(os.environ.get("PADDLE_OCR_MODEL_DIR", str(ROOT / ".local" / "paddleocr")))
    root.mkdir(parents=True, exist_ok=True)
    for name, checksum in MODELS.items():
        archive_path = root / f"{name}_infer.tar"
        if digest(archive_path) != checksum:
            print(f"Downloading Chinese OCR model: {name}", flush=True)
            partial = archive_path.with_suffix(".tar.part")
            try:
                with httpx.stream("GET", f"{BASE_URL}/{archive_path.name}",
                                  follow_redirects=True, timeout=90) as response:
                    response.raise_for_status()
                    with partial.open("wb") as output:
                        for chunk in response.iter_bytes():
                            output.write(chunk)
                if digest(partial) != checksum:
                    raise RuntimeError(f"Chinese OCR model checksum mismatch: {name}")
                partial.replace(archive_path)
            finally:
                partial.unlink(missing_ok=True)
        directory = root / f"{name}_infer"
        directory.mkdir(exist_ok=True)
        with tarfile.open(archive_path) as archive:
            # Copy only the three expected regular files, never archive paths or links.
            for file in ("inference.json", "inference.pdiparams", "inference.yml"):
                member = archive.getmember(f"{name}_infer/{file}")
                if not member.isfile():
                    raise RuntimeError(f"Invalid model archive member: {member.name}")
                with archive.extractfile(member) as source, (directory / file).open("wb") as output:
                    shutil.copyfileobj(source, output)
        print(f"Verified and installed {name}", flush=True)


if __name__ == "__main__":
    install()
