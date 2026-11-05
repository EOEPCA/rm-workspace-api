#!/usr/bin/env bash
# Keep the served UI available until its replacement is built and checked.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DIST="$ROOT/dist"
LUIGI="$ROOT/luigi-shell"
MGMT="$ROOT/management"
stage_dir="$(mktemp -d "$ROOT/.tmp-dist.XXXXXX")"
build_dir="$(mktemp -d "$ROOT/.tmp-build.XXXXXX")"
trap 'rm -rf "$stage_dir" "$build_dir"' EXIT

rsync -a \
  --exclude 'node_modules' \
  --exclude 'dist' \
  --exclude '.quasar' \
  --exclude '.env*' \
  --exclude '.npmrc' \
  "$MGMT"/ "$build_dir/"

echo "[1/4] Build Quasar app (management) ..."
pushd "$build_dir" >/dev/null
npm ci
npm run build
popd >/dev/null

echo "[2/4] Stage Luigi shell ..."
rsync -a --delete \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude '.idea' \
  --exclude '.vscode' \
  "$LUIGI"/ "$stage_dir"/

echo "[3/4] Stage Quasar build ..."
mkdir -p "$stage_dir/management"
rsync -a --delete "$build_dir/dist/" "$stage_dir/management/"
test -f "$stage_dir/ui.html"
test -f "$stage_dir/management/index.html"

echo "[4/4] Update deployment folder ..."
mkdir -p "$DIST"
rsync -a --delay-updates --delete-delay "$stage_dir/" "$DIST"/

echo "✅ Done. Final deploy folder: $DIST"
echo "   - Luigi shell files at:      $DIST/"
echo "   - Quasar (management) at:    $DIST/management/"
