#!/usr/bin/env bash

# Label tool calls for a dataset.
# Prerequisite: Start the SGLang server first via sglang.sh


DATASET="cabra"  # change to "swebench" if you're labeling swe_bench_tool_calls
INPUT_PATH="local_data"
OUTPUT_DIR="local_data/tool_call_results"

set -euo pipefail

args=(
  --dataset "$DATASET"
  --input "$INPUT_PATH"
  --output-dir "$OUTPUT_DIR"
  --n-parallel 100 # you can parallelize the calls with enough RAM / CPU
)

uv run python -m analysis.tool_calls.classifier "${args[@]}" "$@"
