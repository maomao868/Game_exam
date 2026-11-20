# Fixed game test environments

Images pin their Python base by OCI digest and install explicit Python dependency versions with `--no-deps`. TowerMind uses Python 3.10.12 for ML-Agents compatibility. See the [TowerMind adapter notes](../../benchmarks/towermind/README.md) for its offline simulator and two-container checks. `common` needs no native game package. Each adapter has an independent image and missing dependencies fail the tests. The existing required `invariants` job depends on common unit tests and all adapter matrix jobs.

```bash
docker build -f game_first_exam/tests/envs/common.Dockerfile -t game-tests:common .
docker run --rm -v "$PWD:/repo:ro" game-tests:common bash game_first_exam/tests/run.sh common
# Repeat with minigrid, crafter, textworld, babaisai, minihack for the adapter environments.
docker build -f game_first_exam/tests/envs/textworld.Dockerfile -t game-tests:textworld .
docker run --rm -v "$PWD:/repo:ro" game-tests:textworld bash game_first_exam/tests/run.sh textworld
```

The adapter dependency locks match runtime requirements: MiniGrid `requirements-v2.txt`, Crafter and TextWorld `requirements.txt`. System packages are installed from Debian repositories; these are not fully hermetic rebuilds. Evaluation snapshots capture actual runtime image IDs/platforms and should accompany results.

TextWorld 1.7.0 only publishes an x86-tagged wheel containing Python code and authoring executables. For frozen `.z8` games we stage this wheel under `/opt/textworld` and use native Jericho 3.3.1; no bundled x86 authoring executable runs in the test/evaluation path. `check_textworld.py` verifies TextWorld requirements and rejects Python native extensions in the staged wheel. `PYTHONPATH= pip check` validates native dependencies independently, avoiding the intentionally foreign wheel tag. Shared contract tests then execute every frozen game through native Jericho. This packaging profile is explicit; it does not claim upstream publishes a native ARM wheel.

Changing common protocol code requires updating the files-only image version/digest and freezing each task again. Run `scripts/run_games.py --suite core --validate-only`, task normalization checks, common tests and all five adapter environments before a new evaluation. Task generation scripts are not committed; frozen assets and runtime inputs are.

Baba Is AI has a separate fixed legacy Gym 0.25.0 / NumPy 1.26.4 environment, native-equivalence/seed/end-boundary tests, and unchanged vendored upstream source. Its two frozen tasks belong to a minimal smoke suite.

MiniHack has its own pinned NLE 1.1.0 / Gymnasium 1.0.0 environment. The unmodified MiniHack source archive is pinned by commit and SHA256; build tools are pinned and installed before building it without isolation. Tests compare complete native observation arrays, rewards and end flags at every reference step, native abort with negative return, read-only observation, and fresh-process seed reproduction. Room/River are the original smoke subset; the separate minihack-balrog suite adds eight tasks, and Room also has a privileged configuration.

MiniHack suite 0.1.1 also pins the simulator calendar to 2026-11-13 12:00:00 UTC using hash-verified upstream libfaketime 0.9.12. Seed alone cannot reproduce NetHack moon-phase/Friday-the-13th behavior. The test image uses the same calendar with real monotonic time, tests native initialization across three dates, and rejects an unpinned clock. The upstream source archive hash is recorded in the build-time installer; execution is currently validated on ARM64.
