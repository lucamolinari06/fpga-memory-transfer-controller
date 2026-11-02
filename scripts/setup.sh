#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
case "$(uname -s)" in
    Darwin) exec bash scripts/setup_local_macos.sh ;;
    Linux)
        echo 'For Debian/Ubuntu or WSL Ubuntu, first install:'
        echo 'sudo apt-get update && sudo apt-get install verilator build-essential python3 python3-venv git'
        bash scripts/check_tools.sh
        python3 -m venv .venv
        bash scripts/lint.sh
        bash scripts/smoke.sh
        ;;
    *) echo 'Use Linux or WSL Ubuntu; see docs/setup.md.' >&2; exit 1 ;;
esac
