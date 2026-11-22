"""Check a native Harbor trial, including collection hooks that Harbor treats as best effort."""
import hashlib
import json
import sys
from pathlib import Path


def check(job):
    [result_path] = job.glob("*/result.json")
    trial = result_path.parent
    result = json.loads(result_path.read_text())
    assert result["exception_info"] is None, result["exception_info"]
    assert result["agent_info"]["name"] == "oracle"
    assert not (trial / "agent/exit-code.txt").exists(), (trial / "agent/oracle.txt").read_text()
    artifacts = trial / "artifacts"
    manifest = json.loads((artifacts / "manifest.json").read_text())
    expected = {"final.json", "episode.jsonl", "collection.ready", "sim-hostname.txt"}
    evidence = [entry for entry in manifest if entry["source"].startswith("/data/")]
    assert len(evidence) == len(expected)
    assert {e["source"] for e in evidence} == {f"/data/{name}" for name in expected}
    assert all(e["service"] == "sim" and e["status"] == "ok" for e in evidence), evidence

    log = (trial / "trial.log").read_text()
    assert log.index("Main service stopped") < log.index("Collect hook in service 'sim' completed")
    final_path = artifacts / "data/final.json"
    digest = hashlib.sha256(final_path.read_bytes()).hexdigest()
    verifier = trial / "verifier"
    assert (verifier / "evidence.sha256").read_text().split()[0] == digest
    assert not (verifier / "agent-stage-marker").exists()
    roles = {role: path.read_text().strip() for role, path in {
        "agent": artifacts / "logs/artifacts/agent-hostname.txt",
        "sim": artifacts / "data/sim-hostname.txt",
        "verifier": verifier / "verifier-hostname.txt",
    }.items()}
    assert all(roles.values()) and len(set(roles.values())) == 3, roles

    final = json.loads(final_path.read_text())
    events = [json.loads(line) for line in (artifacts / "data/episode.jsonl").read_text().splitlines()]
    assert [e["action"] for e in events if e["event"] == "step"] == ["interact"]
    assert events[-1] == {"event": "final", **final}
    assert final["schema"] == "game-standard/2.2" and final["benchmark"] == "overcooked"
    assert final["reason"] == "agent_finished" and final["steps"] == 1
    reward = json.loads((verifier / "reward.json").read_text())
    assert reward["steps"] == 1 and reward["result_valid"] == 1 and reward["infra_error"] == 0
    assert reward["primary_score"] == final["metrics"]["native_return"]
    print(json.dumps({"containers": roles, "final_sha256": digest, "reason": final["reason"],
                      "steps": reward["steps"], "primary_score": reward["primary_score"]}, indent=2))


if __name__ == "__main__":
    check(Path(sys.argv[1]))
