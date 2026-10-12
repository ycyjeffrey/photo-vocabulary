import hashlib
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    print(f"Downloading missing OCR model: {path.name}")
    sys.exit(1)
if hashlib.sha256(path.read_bytes()).hexdigest() != sys.argv[2]:
    print(f"OCR model checksum mismatch: {path}")
    sys.exit(1)
