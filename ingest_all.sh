#!/usr/bin/env bash
set -euo pipefail
PATTERN="${1:-data/inbound/*.edi}"
echo "Ingesting files matching: $PATTERN"
for f in $PATTERN; do
  echo ""
  echo "=== $(basename "$f") ==="
  python -m app.ingest "$f"
done
echo ""
echo "Done."
