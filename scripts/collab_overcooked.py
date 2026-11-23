"""Prepare native Collab-Overcooked recipe groups and hand them to Harbor."""
import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib


def select(catalog, families, include, exclude, limit):
    levels = catalog["levels"]
    if set(families) - levels.keys():
        raise ValueError("Unknown recipe family (choose level_1 through level_6)")
    orders = [order for level, group in levels.items() if not families or level in families
              for order in group if (not include or any(fnmatch.fnmatchcase(order, p) for p in include))
              and not any(fnmatch.fnmatchcase(order, p) for p in exclude)]
    if limit is not None:
        orders = orders[:limit]
    if not orders:
        raise ValueError("No matching Collab-Overcooked recipes")
    return orders


def build_images(source, catalog, smoke):
    digest = hashlib.sha256(catalog["revision"].encode())
    for file in sorted(source.iterdir()):
        if file.is_file():
            digest.update(file.read_bytes())
    images = {}
    for target in ("sim", "probe" if smoke else "role", "grader"):
        tag = f"game-exam-collab-{target}:{digest.hexdigest()[:16]}"
        upstream = catalog["source"] + "#" + catalog["revision"]
        subprocess.run(["docker", "build", "--build-context", "upstream=" + upstream,
                        "--target", target, "-t", tag, str(source)], check=True)
        images[target] = tag
    return images


def prepare(source, dest, orders, catalog, model, smoke, images):
    repeats = 1 if smoke else catalog["repetitions"]
    policy = "offline-fixture" if smoke else "upstream-llmpair"
    tasks = []
    for order in orders:
        task = dest / ("collab-" + order.replace("_", "-"))
        replacements = {"SIM_IMAGE": images["sim"], "ROLE_IMAGE": images["probe" if smoke else "role"],
                        "GRADER_IMAGE": images["grader"], "ORDER_NAME": order, "ORDER_SLUG": task.name,
                        "EPISODES": str(repeats), "TRIAL_TIMEOUT": str(1800 * repeats if smoke else 86400),
                        "MODEL_NAME": model, "REVISION": catalog["revision"], "POLICY": policy}
        for file in (source / "task").rglob("*"):
            if not file.is_file():
                continue
            target = task / file.relative_to(source / "task")
            target.parent.mkdir(parents=True, exist_ok=True)
            content = file.read_text(encoding="utf-8")
            if file.name == "docker-compose.yaml" and file.parent.name == "environment":
                for role in ("Chef", "Assistant"):
                    mount = '    volumes: ["' + role.lower() + ':/role:ro"]'
                    network = "    network_mode: none" if smoke else "    networks: [" + role.lower() + "_egress]"
                    settings = "COLLAB_PROBE: '1'" if smoke else 'OPENAI_BASE_URL: "${OPENAI_BASE_URL:-https://api.openai.com/v1}"'
                    content = content.replace("{ROLE: " + role + ", MODEL: MODEL_NAME}",
                                              "{ROLE: " + role + ", MODEL: MODEL_NAME, " + settings + "}")
                    content = content.replace(mount, mount + "\n" + network)
                if not smoke:
                    content = content.replace("    read_only: true", "    secrets: [model_key]\n    read_only: true")
                    content += "\nnetworks:\n  chef_egress: {}\n  assistant_egress: {}\nsecrets:\n  model_key:\n    environment: COLLAB_API_KEY\n"
            for key, value in replacements.items():
                content = content.replace(key, value)
            target.write_text(content, encoding="utf-8", newline="\n")
        (task / "tests/selection.json").write_text(json.dumps([order, model, repeats]))
        tasks.append({"path": str(task)})
    config = {"tasks": tasks, "agents": [{"name": "oracle"}], "n_attempts": 1,
              "n_concurrent_trials": 1, "retry": {"max_retries": 0}}
    path = dest / "job.json"
    path.write_text(json.dumps(config, indent=2))
    return path


def launch(root, families, include, exclude, limit, listing, args, harbor):
    catalog = tomllib.loads((root / "configs/native_benchmarks/collab-overcooked.toml").read_text())
    parser = argparse.ArgumentParser(prog="harbor run --game-suite collab-overcooked")
    parser.add_argument("--offline-smoke", action="store_true", help="fixed boiled-egg responses, no model calls")
    parser.add_argument("-m", "--model", default="gpt-4o")
    parser.add_argument("--job-name")
    parser.add_argument("--jobs-dir", type=Path)
    parser.add_argument("-y", "--yes", action="store_true")
    options = parser.parse_args(args)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)?", options.model):
        raise ValueError("Invalid upstream model identifier")
    if options.model == "human" or ("gpt" in options.model.lower() and options.model not in {"gpt-4o", "gpt-3.5-turbo-0125"}):
        raise ValueError("Select a supported upstream chat model (e.g. gpt-4o)")
    orders = select(catalog, families, include, exclude, limit)
    if options.offline_smoke:
        if "boiled_egg" not in orders or options.model != "gpt-4o":
            raise ValueError("The offline smoke fixture covers boiled_egg with the gpt-4o prompt format")
        orders = ["boiled_egg"]
    if listing:
        print("\n".join(orders))
        return 0
    if not options.offline_smoke and not os.environ.get("COLLAB_API_KEY"):
        raise ValueError("Set COLLAB_API_KEY for the native model or select --offline-smoke")
    source = root / "game_first_exam/benchmarks/collab_overcooked"
    images = build_images(source, catalog, options.offline_smoke)
    prepared = root / "jobs/prepared"
    prepared.mkdir(parents=True, exist_ok=True)
    dest = Path(tempfile.mkdtemp(prefix="collab-", dir=prepared))
    config = prepare(source, dest, orders, catalog, options.model, options.offline_smoke, images)
    argv = ["run", "-c", str(config)]
    if options.job_name:
        argv.extend(["--job-name", options.job_name])
    if options.jobs_dir:
        argv.extend(["--jobs-dir", str(options.jobs_dir)])
    if options.yes:
        argv.append("-y")
    return harbor(argv)
