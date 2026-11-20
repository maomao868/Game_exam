"""Development instance for tests only. No task or suite registration."""
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "game_first_exam/runtime"
BENCHMARK = ROOT / "game_first_exam/benchmarks/towermind"
sys.path[:0] = [str(RUNTIME), str(BENCHMARK)]

import instance_schema
from config_schema import PROTOCOL, INSTANCE_SCHEMA, register_instance_schema


register_instance_schema(instance_schema)


def instance():
    return {
        "schema_version": INSTANCE_SCHEMA, "protocol": PROTOCOL, "adapter_version": "1.0.0",
        "capabilities": dict(instance_schema.CAPABILITIES),
        "benchmark": "towermind", "env_id": "TowerMind-Level-0", "family": "development",
        "level_id": 0, "seed": 42, "max_steps": None, "initial_state_sha256": "0" * 64,
        "engine_versions": dict(instance_schema.ENGINE_VERSIONS),
        "engine_archive_sha256": instance_schema.ARCHIVE_SHA256,
        "observation_profile": "player-rgb-v1",
        "metric_spec": {
            "primary": "native_return", "success_label": "native_level_completed",
            "reducer": "family_macro", "reducer_version": "1.0.0",
        },
    }


def serve():
    """Launch the real public HTTP handler with a development instance for the peer-container probe."""
    from http.server import HTTPServer
    import signal
    from tempfile import TemporaryDirectory

    from adapter import Adapter
    from server import Game, Handler

    def stop(*_):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    config = instance()
    with TemporaryDirectory() as directory:
        adapter = Adapter(config)
        config["initial_state_sha256"] = adapter.fingerprint()
        game = Game(adapter, config, directory, wall_clock=180)
        try:
            if game.final is not None:
                raise RuntimeError("TowerMind development simulator initialization failed")
            with HTTPServer(("0.0.0.0", 8000), Handler) as server:
                server.game = game
                server.serve_forever()
        finally:
            game.close()


if __name__ == "__main__":
    serve()
