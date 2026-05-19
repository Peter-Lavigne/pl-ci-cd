#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f "pyproject.toml" ]]; then
  echo "Run this from your project root (where pyproject.toml lives)."
  exit 1
fi

export UV_PUBLISH_TOKEN="${UV_PUBLISH_TOKEN:-$(cat ~/.secrets-files/UV_PUBLISH_TOKEN)}"

echo 'Running "rm -f dist/*.whl dist/*.tar.gz"...'
rm -f dist/*.whl dist/*.tar.gz

echo 'Running "uv version --bump patch"...'
uv version --bump patch

echo 'Running "uv build --no-sources -o dist"...'
uv build --no-sources -o dist

echo 'Running "uv publish dist/*"...'
uv publish dist/*

echo 'Running "git add -A && git commit"...'
git add -A
git commit -m "Bump version to $(uv version --short)"

echo 'Release complete.'
