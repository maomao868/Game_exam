"""Compare the Harbor split to a direct run of the unedited upstream benchmark."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def check_live_isolation(catalog):
    import yaml
    sys.path.insert(0, str(ROOT / "scripts"))
    from collab_overcooked import prepare

    images = {"sim": "sim", "role": "role", "grader": "grader"}
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        source = ROOT / "game_first_exam/benchmarks/collab_overcooked"
        prepare(source, dest, ["boiled_egg"], catalog, "gpt-4o", False, images)
        task = dest / "collab-boiled-egg"
        config = yaml.safe_load((task / "environment/docker-compose.yaml").read_text())
        services = config["services"]
        for role in ("chef", "assistant"):
            assert services[role]["volumes"] == [role + ":/role:ro"]
            assert services[role]["secrets"] == ["model_key"]
            assert services[role]["read_only"] and services[role]["cap_drop"] == ["ALL"]
            assert "COLLAB_PROBE" not in services[role]["environment"]
        assert not set(services["chef"]["networks"]).intersection(services["assistant"]["networks"])
        assert all(services[name]["network_mode"] == "none" and "secrets" not in services[name]
                   for name in ("sim", "main"))
        assert int(services["sim"]["environment"]["REPEATS"]) == 10
        assert (task / "solution/solve.sh").stat().st_mode & 0o001


def main(job, upstream):
    catalog = tomllib.loads((ROOT / "configs/native_benchmarks/collab-overcooked.toml").read_text())
    head = subprocess.check_output(["git", "-C", upstream, "rev-parse", "HEAD"], text=True).strip()
    assert head == catalog["revision"]
    levels = {node.targets[0].id: ast.literal_eval(node.value)
              for node in ast.parse((upstream / "src/convert_result.py").read_text()).body
              if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
              and node.targets[0].id.startswith("level_")}
    assert levels == catalog["levels"]
    check_live_isolation(catalog)
    [trial_result] = job.glob("*/result.json")
    trial = trial_result.parent
    result = json.loads(trial_result.read_text())
    assert result["exception_info"] is None, result["exception_info"]
    assert not (trial / "agent/exit-code.txt").exists(), (trial / "agent/oracle.txt").read_text()
    data = trial / "artifacts"
    manifest = json.loads((data / "manifest.json").read_text())
    assert any(a["source"] == "/evidence" and a["service"] == "sim" and a["status"] == "ok" for a in manifest)
    timeline = (trial / "trial.log").read_text()
    assert timeline.index("Main service stopped") < timeline.index("Collect hook in service 'sim' completed")
    [evaluated] = (data / "evidence").rglob("experiment_*.json")
    rewards = json.loads((trial / "verifier/reward.json").read_text())
    assert rewards == {"SR": 1.0, "PC": 1.0, "IC": 1.0, "RC": 1.0}, rewards
    assert result["verifier_result"]["rewards"] == rewards
    [config] = (job.parent / "prepared").glob("collab-*/job.json")
    task = Path(json.loads(config.read_text())["tasks"][0]["path"])
    import yaml
    services = yaml.safe_load((task / "environment/docker-compose.yaml").read_text())["services"]
    sim = services["sim"]["image"]
    for name in ("chef", "assistant"):
        assert services[name]["network_mode"] == "none" and services[name]["read_only"]
        assert services[name]["volumes"] == [name + ":/role:ro"]
    for name in ("sim", "chef", "assistant", "main"):
        assert services[name]["network_mode"] == "none"
    checks = {"main.py": "src/main.py", "collab/collab.py": "src/collab/collab.py",
              "collab/modules.py": "src/collab/modules.py",
              "/bench/lib/overcooked_ai_py/mdp/overcooked_mdp.py": "lib/overcooked_ai/overcooked_ai_py/mdp/overcooked_mdp.py"}
    grader = (task / "tests/Dockerfile").read_text().splitlines()[0].split()[1]
    for image, files in ((sim, checks), (grader, {"eval_utils.py": "src/eval_utils.py", "time_step.py": "src/time_step.py"})):
        hashes = subprocess.check_output(["docker", "run", "--rm", "--network", "none", image,
                                          "sha256sum", *files], text=True).splitlines()
        for line, path in zip(hashes, files.values(), strict=True):
            assert line.split()[0] == hashlib.sha256((upstream / path).read_bytes()).hexdigest(), path
    direct = subprocess.check_output([
        "docker", "run", "--rm", "--network", "none",
        "-v", f"{ROOT}/game_first_exam/tests/collab_native_probe.py:/integration/direct.py:ro",
        "-v", f"{ROOT}/game_first_exam/benchmarks/collab_overcooked/fixture_policy.py:/integration/fixture_policy.py:ro",
        sim, "sh", "-ec", "python /integration/direct.py /tmp/golden >&2 && cat /tmp/golden/*/*/experiment_*.json",
    ])
    assert json.loads(evaluated.read_text()) == json.loads(direct), "Native trajectories differ"
    print("PASS: sealed Harbor trajectory matches direct native run; SR=PC=IC=RC=1")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
