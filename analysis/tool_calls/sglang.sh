#!/usr/bin/env bash

# script to load sglang. you need an env called .venv-sglang that has it installed
# I followed: https://wilsonwu.me/en/blog/2025/getting-started-with-sglang/

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"

# add the path to your .venv
source .venv-sglang/bin/activate

if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  source "$REPO_ROOT/.env"
  set +a
fi


exec python -m sglang.launch_server \
  --model-path Qwen/Qwen3-4B-Instruct-2507 \
  --host 0.0.0.0 \
  --port 30000 \
  --tp-size 1 \
  --dp-size 2 \
  --context-length 10000


# You can check if sglang is working properly with the following command: 

# curl http://127.0.0.1:30000/v1/chat/completions \
#   -H "Content-Type: application/json" \
#   -H "Authorization: Bearer EMPTY" \
#   -d '{
#     "model": "Qwen/Qwen3-4B-Instruct-2507",
#     "messages": [
#       {"role": "system", "content": "You are a helpful assistant."},
#       {"role": "user", "content": "Introduce yourself in two sentences."}
#     ],
#     "max_tokens": 128,
#     "temperature": 0.2
#   }'