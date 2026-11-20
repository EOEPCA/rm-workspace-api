#!/usr/bin/env bash
# Scan tracked files without local caches or ignored configuration.

set -euo pipefail

scan_dir="$(mktemp -d)"
trap 'rm -rf "$scan_dir"' EXIT

git ls-files -z | while IFS= read -r -d '' path; do
  if [[ -f "$path" && ! -L "$path" ]]; then
    mkdir -p "$scan_dir/$(dirname -- "$path")"
    cp -- "$path" "$scan_dir/$path"
  fi
done

gitleaks dir --redact --no-banner --gitleaks-ignore-path .gitleaksignore "$scan_dir"
