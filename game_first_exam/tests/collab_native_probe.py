"""Drive the pristine upstream CLI with the same deterministic role responses as CI."""
import os
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

from collab import collab, modules
from fixture_policy import choose


def query(planner, key, proxy, **options):
    return choose(planner.name, planner.query_messages(options.get("rethink", False)))


if __name__ == "__main__":
    output = Path(sys.argv[1]).resolve()
    sys.argv = ["main.py", "--order", "boiled_egg", "--gpt_model", "gpt-4o",
                "--statistics_save_dir", str(output)]
    with patch.object(modules.Module, "query", query), patch.object(
        collab, "if_two_sentence_similar_meaning", lambda key, proxy, left, right: left == right
    ):
        runpy.run_path(os.path.abspath("main.py"), run_name="__main__")
