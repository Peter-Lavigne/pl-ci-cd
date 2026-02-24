#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f "pyproject.toml" ]]; then
  echo "Run this from your project root (where pyproject.toml lives)."
  exit 1
fi

if [[ -z "${UV_PUBLISH_TOKEN:-}" ]]; then
  echo "UV_PUBLISH_TOKEN is not set. Please set it in your environment."
  exit 1
fi

echo 'Running "uv run check --fix"...'
uv run check --fix

echo 'Running "rm -f dist/*.whl dist/*.tar.gz"...'
rm -f dist/*.whl dist/*.tar.gz

echo 'Running "uv version --bump patch"...'
uv version --bump patch

echo 'Running "uv build --no-sources"...'
uv build --no-sources

echo 'Running "uv publish"...'
uv publish

echo 'Running "git add -A..."'
git add -A

echo 'Running "git commit -m "Bump version to $(uv version --short)"..."'
git commit -m "Bump version to $(uv version --short)"

echo 'Running "git push"...'
git push

echo 'Release complete.'
