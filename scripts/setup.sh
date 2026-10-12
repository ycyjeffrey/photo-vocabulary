#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v tesseract >/dev/null || {
  echo "Install Tesseract first: brew install tesseract (macOS), or apt install tesseract-ocr (Linux)."
  exit 1
}
python3 -m venv .venv
.venv/bin/python -m pip install --quiet -r backend/requirements.lock.txt
mkdir -p .local/tessdata
model_revision=e12c65a915945e4c28e237a9b52bc4a8f39a0cec
for language in eng chi_tra; do
  if [ "$language" = eng ]; then
    checksum=8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba
  else
    checksum=1aa60488574cafa69486d919284f079ca9b68fcc7f6ad8dc1ff1b318dfd97028
  fi
  if ! .venv/bin/python scripts/verify_model.py ".local/tessdata/$language.traineddata" "$checksum"; then
    curl --fail --location --retry 3 \
      "https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/$model_revision/$language.traineddata" \
      --output ".local/tessdata/$language.traineddata.part"
    .venv/bin/python scripts/verify_model.py ".local/tessdata/$language.traineddata.part" "$checksum"
    mv ".local/tessdata/$language.traineddata.part" ".local/tessdata/$language.traineddata"
  fi
done
npm --prefix frontend ci --no-audit --no-fund
npm --prefix frontend run build
echo "Ready. Start with: bash scripts/run.sh"
