"""Run inside the client-only Docker image against the live simulator."""
import base64
from importlib.util import find_spec
from pathlib import Path

from game_client import GameClient


def main():
    assert find_spec("overcooked_ai_py") is None
    assert not Path("/srv/instance.json").exists() and not Path("/data").exists()
    client = GameClient(url="http://sim:8000", startup_timeout=180)
    assert client.spec()["reset_budget"] == 0
    initial = client.observe()
    assert initial["step"] == 0
    result = client.step("interact", expected_step=0, request_id="probe")
    assert result == client.step("interact", expected_step=0, request_id="probe")
    assert result["step"] == 1 and set(result["observation"]) == {"image_png_base64"}
    frame = base64.b64decode(result["observation"]["image_png_base64"], validate=True)
    assert frame.startswith(b"\x89PNG\r\n\x1a\n")
    for endpoint in ("/reset", "/state", "/data/final.json"):
        try:
            client.request(endpoint)
        except ValueError as error:
            assert "unknown endpoint" in str(error)
        else:
            raise AssertionError(f"unexpected public endpoint {endpoint}")
    print("Overcooked client verified one native step through the public interface")


if __name__ == "__main__":
    main()
