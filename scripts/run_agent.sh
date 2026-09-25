#!/bin/zsh
# Run from any location; reports remain in the project directory.
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_dir"
exec python3 -m ai.agent "$@"
