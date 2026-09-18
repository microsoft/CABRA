#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

echo "Scoring existing responses; all background evaluations must be complete."

bash experiments/function_traversal/score.sh
bash experiments/function_search/score.sh
bash experiments/runtime_resolution/score.sh
bash experiments/add_instructions/score.sh
bash experiments/merge_codebases/score.sh