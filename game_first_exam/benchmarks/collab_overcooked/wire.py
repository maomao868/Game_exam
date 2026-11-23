"""One request and one response on an already role-bound Unix socket."""
import json

LIMIT = 2 * 1024 * 1024


def send(stream, value):
    data = json.dumps(value, allow_nan=False).encode() + b"\n"
    if len(data) > LIMIT:
        raise ValueError("Collab-Overcooked message exceeds size limit")
    stream.write(data)
    stream.flush()


def receive(stream):
    data = stream.readline(LIMIT + 1)
    if not data.endswith(b"\n") or len(data) > LIMIT:
        raise ValueError("Incomplete or oversized Collab-Overcooked message")
    return json.loads(data)
