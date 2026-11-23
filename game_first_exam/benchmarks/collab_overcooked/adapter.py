"""Run the upstream episode, moving only role inference across the isolation boundary."""
import os
from pathlib import Path
import runpy
import socket
import subprocess
import sys
import time

from wire import receive, send

ROLES = ("Chef", "Assistant")


def episode():
    from collab import collab, modules

    listeners = {}
    for role in ROLES:
        path = Path("/channels") / role / "planner.sock"
        path.unlink(missing_ok=True)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(path))
        path.chmod(0o666)
        listener.listen(1)
        listener.settimeout(300)
        listeners[role] = listener

    def call(role, request):
        conn, _ = listeners[role].accept()
        with conn, conn.makefile("rwb") as stream:
            conn.settimeout(300)
            send(stream, request)
            answer = receive(stream)
        if "error" in answer:
            raise RuntimeError(f"{role} inference failed: {answer['error']}")
        return answer["value"]

    def query(planner, key, proxy, **options):
        # Upstream uses map only for its interactive human UI.
        options.pop("map", None)
        data = call(planner.name, {"op": "plan", "head": planner.instruction_head_list,
                    "user": planner.current_user_message, "options": options})
        response, tokens, updated = data
        if not isinstance(response, str) or type(tokens) is not int or tokens < 0:
            raise ValueError("Invalid role response")
        if updated is not None:
            if not isinstance(updated, str) or not planner.current_user_message["content"].startswith(updated):
                raise ValueError("Invalid retry context")
            planner.current_user_message["content"] = updated
        return response, tokens

    # Upstream compares two spoken lines only while this role answers a teammate.
    original_answer = collab.LLMAgents.answer
    def answer(agent, *args, **kwargs):
        def similar(key, proxy, first, second):
            result = call(agent.name, {"op": "similar", "lines": [first, second]})
            if type(result) is not bool:
                raise ValueError("Invalid similarity result")
            return result
        previous = collab.if_two_sentence_similar_meaning
        collab.if_two_sentence_similar_meaning = similar
        try:
            return original_answer(agent, *args, **kwargs)
        finally:
            collab.if_two_sentence_similar_meaning = previous

    modules.Module.query = query
    collab.LLMAgents.answer = answer
    game_args = ["main.py", "--layout", "new_env", "--p0", "LLMPair", "--p1", "LLMPair",
                 "--episode", "1", "--horizon", "120", "--test_mode", "fix_task",
                 "--order", os.environ["ORDER"], "--gpt_model", os.environ["MODEL"],
                 "--statistics_save_dir", "/evidence/raw"]
    sys.argv = game_args
    runpy.run_path("main.py", run_name="__main__")


def run():
    status = Path("/status/state")
    try:
        for _ in range(int(os.environ["REPEATS"])):
            subprocess.run([sys.executable, __file__, "episode"], check=True)
        status.write_text("complete")
    except Exception:
        status.write_text("failed")
        raise
    # Harbor collects sidecar files after the main environment stops.
    while True:
        time.sleep(60)


if __name__ == "__main__":
    if sys.argv[1:] == ["episode"]:
        episode()
    else:
        run()
