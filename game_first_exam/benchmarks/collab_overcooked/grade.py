"""Evaluate a sealed set of complete native logs using the authors' two scoring stages."""
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from eval_utils import Evaluation, ExpLog


def grade(order, model, repeats, evidence, output):
    raw = evidence / "raw" / model / order
    logs = sorted(raw.glob("experiment_*.json"))
    if len(logs) != repeats:
        raise ValueError(f"Expected {repeats} complete episodes, collected {len(logs)}")
    for log in logs:
        data = json.loads(log.read_text())
        ticks = data["total_timestamp"]
        if (not ticks or ticks != list(range(len(ticks))) or len(data["content"]) != len(ticks)
                or data["total_order_finished"] not in ([], [order])
                or (not data["total_order_finished"] and len(ticks) != 120)):
            raise ValueError(f"Incomplete native trajectory in {log.name}")
    # time_step.py hardcodes this directory label. It operates only on logs,
    # and never consults the model name while applying the timing rule.
    label = Path("deepseek-ai/DeepSeek-V3")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        input_dir = root / "src/data" / label / order
        input_dir.mkdir(parents=True)
        for log in logs:
            shutil.copyfile(log, input_dir / log.name)
        subprocess.run([sys.executable, str(Path("time_step.py").resolve())], cwd=root, check=True)
        truncated = root / "src/data/truncate_1_5" / label / order
        episodes = ExpLog(str(truncated))
        if len(episodes) != repeats:
            raise ValueError("The native evaluator did not load every episode")
        output.mkdir(exist_ok=True, parents=True)
        result = Evaluation(order_name_list=[order] * repeats, exp_log=episodes).evaluate(str(output))[order]
    tes = result["average"]["similarity_and_redundancy"]
    scores = {"SR": result["task_metrics"]["success_rate"],
              "PC": (tes["agent_0"]["mean_f1"] + tes["agent_1"]["mean_f1"]) / 2,
              "IC": result["statistic"]["initiate_collaboration"],
              "RC": result["statistic"]["respond_collaboration"]}
    if not all(math.isfinite(value) and 0 <= value <= 1 for value in scores.values()):
        raise ValueError("Invalid native metric")
    (output / "reward.json").write_text(json.dumps(scores, allow_nan=False))
    return scores


if __name__ == "__main__":
    order, model, repeats = json.loads(Path("/tests/selection.json").read_text())
    grade(order, model, repeats, Path("/evidence"), Path("/logs/verifier"))
