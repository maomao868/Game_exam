"""Exercise the public interface from a container built with only client-side files."""
import base64
from pathlib import Path
import socket

from game_client import GameClient


def main():
    client = GameClient(url="http://sim:8000", startup_timeout=120)
    spec = client.spec()
    assert spec["reset_budget"] == 0
    assert "seed" not in spec and "engine_archive_sha256" not in spec
    obs = client.observe()
    assert set(obs["observation"]) == {"image_png_base64"}
    assert obs["step"] == 0
    assert base64.b64decode(obs["observation"]["image_png_base64"], validate=True).startswith(b"\x89PNG\r\n\x1a\n")
    try:
        with socket.create_connection(("sim", 5005), timeout=3):
            raise AssertionError("the simulator's loopback RPC port is reachable from the client")
    except (ConnectionRefusedError, TimeoutError):
        pass
    for private_path in ("/opt/towermind", "/repo", "/srv", "/data"):
        assert not Path(private_path).exists(), f"unexpected sim path in client: {private_path}"
    obs = client.step("0 0 0", expected_step=0)
    assert obs["step"] == 1
    assert set(obs["observation"]) == {"image_png_base64"}
    print("TowerMind public HTTP is usable, with the RPC listener and native assets confined to the simulator")


if __name__ == "__main__":
    main()
