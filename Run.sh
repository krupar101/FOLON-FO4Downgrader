#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
exec "${FOLON_PYTHON:-python3}" FOLON-Downgrader.py "$@"
