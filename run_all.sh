#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

bash experiments/function_traversal/generate_tasks.sh
bash experiments/function_traversal/llm.sh
bash experiments/function_traversal/agent.sh

bash experiments/function_search/generate_tasks.sh
bash experiments/function_search/llm.sh
bash experiments/function_search/agent.sh

bash experiments/runtime_resolution/generate_tasks.sh
bash experiments/runtime_resolution/llm.sh
bash experiments/runtime_resolution/agent.sh

bash experiments/add_instructions/generate_tasks.sh
bash experiments/add_instructions/llm.sh
bash experiments/add_instructions/agent.sh

bash experiments/merge_codebases/generate_tasks.sh
bash experiments/merge_codebases/llm.sh
bash experiments/merge_codebases/agent.sh

echo "Evaluations launched in background tmux sessions."
echo "After all evaluations finish successfully, run: bash score_all.sh"