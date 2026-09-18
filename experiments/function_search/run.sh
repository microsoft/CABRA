#!/bin/bash
# End-to-end: generate tasks, then run the copilot agent scaffold.
# Score separately after these finish if needed.

set -e

dir="$(cd "$(dirname "$0")" && pwd)"

bash "$dir/generate_tasks.sh"
bash "$dir/agent.sh"