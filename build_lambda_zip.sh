#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Defaults match AWS Lambda Python 3.11 on x86_64.
# Override if needed:
#   LAMBDA_PLATFORM=manylinux2014_aarch64 LAMBDA_PY_VERSION=3.11 ./build_lambda_zip.sh
LAMBDA_PY_VERSION="${LAMBDA_PY_VERSION:-3.11}"
LAMBDA_PLATFORM="${LAMBDA_PLATFORM:-manylinux2014_x86_64}"

rm -rf build lambda.zip
mkdir -p build

python3 -m pip install \
  --platform "$LAMBDA_PLATFORM" \
  --implementation cp \
  --python-version "$LAMBDA_PY_VERSION" \
  --only-binary=:all: \
  -r requirements.txt \
  -t build

cp -R app build/

(cd build && zip -r ../lambda.zip .)

echo "Created: $ROOT_DIR/lambda.zip"

