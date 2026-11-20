#!/usr/bin/env bash
# Keep the served UI available until its replacement is built and checked.

set -euo pipefail

if [[ $# -gt 1 || ( $# -eq 1 && "${1:-}" != "--no-cache" ) ]]; then
  echo "Usage: $0 [--no-cache]" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")" && pwd)"
DIST="$ROOT/dist"
stage_dir="$(mktemp -d "$ROOT/.tmp-dist.XXXXXX")"
trap 'rm -rf "$stage_dir"' EXIT

echo "Build the UI with the release toolchain ..."
docker build --pull "$@" --target ui-dist \
  --output "type=local,dest=$stage_dir" "$ROOT/.."
test -f "$stage_dir/ui.html"
test -f "$stage_dir/management/index.html"

echo "Update deployment folder ..."
mkdir -p "$DIST"
rsync -a --delay-updates --delete-delay "$stage_dir/" "$DIST"/

echo "✅ Done. Final deploy folder: $DIST"
echo "   - Luigi shell files at:      $DIST/"
echo "   - Quasar (management) at:    $DIST/management/"
