#!/bin/sh
# D18 gap benchmark runner. See scripts/exp4_gap_benchmark.py.
cd "$(dirname "$0")/.." || exit 1
exec python scripts/exp4_gap_benchmark.py --json outputs/exp4/gap_benchmark.json
