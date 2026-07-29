#!/usr/bin/env bash
set -euo pipefail

stats_file="${1:-}"
if [[ -z "${stats_file}" || ! -f "${stats_file}" ]]; then
  echo "Usage: $0 <stats.txt>" >&2
  exit 1
fi

grep -Ei \
  "simInsts|simOps|numCycles|ipc|branch|mispred|rob|iq|lsq|commit" \
  "${stats_file}" | head -n 160
