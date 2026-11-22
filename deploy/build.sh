#!/usr/bin/env bash
# Package the app plus Linux wheels, so EC2 installs exactly what was built, offline.
# Usage: build.sh <commit-sha> <run-id>
set -euo pipefail
cd "$(dirname "$0")/.."

sha=$1
run=$2
version=$(tr -d '\r\n' < prototype/VERSION)
[[ $version =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?$ ]] || { echo "Bad VERSION: $version" >&2; exit 1; }
[[ $sha =~ ^[0-9a-f]{40}$ ]] || { echo "Bad commit SHA: $sha" >&2; exit 1; }
name="build-v${version}-${run}-${sha:0:7}"

rm -rf dist
mkdir -p dist/stage/app/public dist/stage/wheels
cp prototype/{app,cache,db,worker}.py prototype/VERSION prototype/requirements-aws.txt dist/stage/app/
cp -r prototype/templates dist/stage/app/
cp -r prototype/public/static dist/stage/app/public/
printf '%s\n' "$sha" > dist/stage/app/BUILD
cp deploy/deploy.sh deploy/ticketq.service dist/stage/

python -m pip download --quiet --disable-pip-version-check --no-deps --only-binary=:all: \
  --python-version 3.12 --implementation cp --abi cp312 --abi abi3 --abi none \
  --platform manylinux_2_28_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux2014_x86_64 \
  -r prototype/requirements-aws.txt -d dist/stage/wheels

python -c "import shutil, sys; shutil.make_archive('dist/' + sys.argv[1], 'zip', 'dist/stage')" "$name"
rm -rf dist/stage
(cd dist && sha256sum "$name.zip" | cut -d' ' -f1 > "$name.sha256")
echo "Built $name.zip"
