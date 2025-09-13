#!/usr/bin/env bash
# This script builds the Quasar app in its own directory (management/dist)
# and then copies Luigi shell and the built Quasar app into workspace_ui/dist.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DIST="$ROOT/dist"
LUIGI="$ROOT/luigi-shell"
MGMT="$ROOT/management"

echo "[1/4] Clean deployment folder ..."
rm -rf "$DIST"
mkdir -p "$DIST"

echo "[2/4] Build Quasar app (management) ..."
pushd "$MGMT" >/dev/null
if [ -f package-lock.json ]; then
  npm ci
else
  npm install
fi
npm run build
popd >/dev/null

echo "[3/4] Copy Luigi shell into dist/ ..."
# Copy all needed static assets for Luigi shell; exclude dev folders.
rsync -a --delete \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude '.idea' \
  --exclude '.vscode' \
  "$LUIGI"/ "$DIST"/

echo "[4/4] Copy Quasar build into dist/management ..."
# Keep Quasar under a subfolder to avoid filename collisions with Luigi files.
mkdir -p "$DIST/management"
rsync -a --delete "$MGMT/dist/" "$DIST/management/"

echo "✅ Done. Final deploy folder: $DIST"
echo "   - Luigi shell files at:      $DIST/"
echo "   - Quasar (management) at:    $DIST/management/"
