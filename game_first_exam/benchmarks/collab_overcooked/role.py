"""One role per service. The live path calls the authors' original inference module."""
import os
from pathlib import Path
import socket
import time

from wire import receive, send


def main():
    from collab import modules

    role = os.environ["ROLE"]
    model = os.environ["MODEL"]
    assert role in {"Chef", "Assistant"}
    assert not any(Path(p).exists() for p in (
        "prompts", "main.py", "eval_utils.py", "/evidence", "/channels", "/tests", "/var/run/docker.sock"))
    probe = os.getenv("COLLAB_PROBE") == "1"
    if probe:
        from fixture_policy import choose
        assert sorted(os.listdir("/sys/class/net")) == ["lo"]
    else:
        # The author code reads its key file in the embedding helper and its
        # cached module variable in the chat helper. Both see the same secret.
        modules.gpt4_key_file = "/run/secrets/model_key"
        modules.openai_key = Path(modules.gpt4_key_file).read_text().strip()
        modules.openai.api_base = os.environ["OPENAI_BASE_URL"]
        if not modules.openai_key:
            raise ValueError("Missing model credential")

    while True:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            try:
                conn.connect("/role/planner.sock")
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(0.1)
                continue
            with conn.makefile("rwb") as stream:
                try:
                    try:
                        item = receive(stream)
                    except (ConnectionResetError, ValueError):
                        # Each fresh upstream episode recreates its private sockets.
                        continue
                    if item["op"] == "similar":
                        if probe:
                            value = item["lines"][0] == item["lines"][1]
                        else:
                            value = bool(modules.if_two_sentence_similar_meaning("", "", *item["lines"]))
                    elif item["op"] == "plan":
                        planner = modules.Module(item["head"], model=model, model_dirname="",
                                                local_server_api=os.getenv("OPENAI_BASE_URL"), K=0)
                        planner.current_user_message = item["user"]
                        if probe:
                            value = choose(role, planner.query_messages(False))
                        else:
                            value = planner.query(key="", proxy="", **item["options"])
                            if not value[0]:
                                raise ValueError("Upstream returned an empty model response")
                    else:
                        raise ValueError("Unknown role request")
                except Exception as exc:
                    send(stream, {"error": type(exc).__name__})
                    raise
                send(stream, {"value": value})


if __name__ == "__main__":
    main()
