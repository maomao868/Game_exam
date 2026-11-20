#!/usr/bin/env bash
# Run in the matching pinned image (game_first_exam/tests/envs). Missing dependencies are failures, never skips.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"
case "${1:-common}" in
  common)
    python3 -m unittest discover -s game_first_exam/tests -p 'test_layout.py'
    python3 -m unittest discover -s game_first_exam/tests -p 'test_game_service.py'
    python3 -m unittest discover -s game_first_exam/tests -p 'test_game_configuration.py'
    python3 -m unittest discover -s game_first_exam/tests -p 'test_games_runner.py'
    python3 -m unittest discover -s game_first_exam/tests -p 'test_game_runtime.py'
    python3 -m unittest discover -s game_first_exam/tests -p 'test_game_connection.py'
    python3 -m unittest discover -s game_first_exam/tests -p 'test_game_modes.py'
    ;;
  minihack)
    export GAME_TEST_BENCHMARK=minihack
    python3 game_first_exam/tests/test_game_adapters.py
    python3 game_first_exam/tests/test_minihack.py
    python3 game_first_exam/tests/test_game_modes_native.py
    ;;
  towermind)
    python3 game_first_exam/tests/test_towermind_contract.py
    xvfb-run -a -s "-screen 0 1400x900x24" python3 game_first_exam/tests/test_towermind_native.py
    ;;
  minigrid|crafter|textworld|babaisai)
    export GAME_TEST_BENCHMARK="$1"
    python3 game_first_exam/tests/test_game_adapters.py
    python3 game_first_exam/tests/test_game_native_settings.py
    if [ "$1" = crafter ]; then python3 game_first_exam/tests/test_game_modes_native.py; fi
    if [ "$1" = babaisai ]; then python3 game_first_exam/tests/test_babaisai.py; fi
    ;;
  *) echo "unknown game test environment: $1" >&2; exit 2 ;;
esac
