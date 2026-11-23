#!/usr/bin/env python3
"""Game Exam on native Harbor 0.23.0.

  harbor run --game-suite minihack-balrog --standard --list
  harbor run --game-suite minihack --standard --family room -a oracle
  harbor run --game-suite crafter --realtime -c configs/harbor/codex-deepseek.json

--game-suite chooses frozen game tasks; --standard/--privileged/--realtime,
--benchmark, --family, -i/-x, -p and -l filter the selection. --list validates
without running. --core (default) selects the core game suite; --all selects
all frozen game tasks. Explicit native -p/-c/-d without selection flags and
all other Harbor commands pass through unchanged. Agent/model/options use
Harbor's native configuration. No direct LLM or RL entry point is added.
"""
import fnmatch, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

# --- the task tree: where the tasks and their scripts/ come from -------------------------------------------
REPO_URL = "https://github.com/LAMDA-NeSy/Game_exam.git"
_ROOT: list[Path] = []


def is_tree(d: Path) -> bool:
    return (d / "configs/game_benchmarks.toml").is_file() and (d / "game_first_exam/tasks").is_dir() and (d / "scripts/task_conventions.py").is_file()


def cache_dir() -> Path:
    from importlib.metadata import PackageNotFoundError, version
    try:
        ver = version("game-exam")
    except PackageNotFoundError:
        ver = "main"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "game-exam" / ver


_PEP440 = re.compile(r"v?(?:(?P<epoch>\d+)!)?(?P<release>\d+(?:\.\d+)*)"
                     r"(?:[-_.]?(?P<pre_l>alpha|a|beta|b|preview|pre|c|rc)[-_.]?(?P<pre_n>\d*))?"
                     r"(?P<post>-(?P<post_n1>\d+)|[-_.]?(?:post|rev|r)[-_.]?(?P<post_n2>\d*))?"
                     r"(?P<dev>[-_.]?dev[-_.]?(?P<dev_n>\d*))?(?:\+(?P<local>[a-z0-9]+(?:[-_.][a-z0-9]+)*))?")
_PRE = {"alpha": "a", "a": "a", "beta": "b", "b": "b", "c": "rc", "rc": "rc", "pre": "rc", "preview": "rc"}


def version_key(v: str):
    """A version string after PEP 440 normalization (standard library only), as a comparable key: `1.0.0-preview`,
    `v1.0.0rc0` and `1.0.0rc0` give the same key; None when v is no PEP 440 version."""
    m = _PEP440.fullmatch(v.strip().lower())
    if not m:
        return None
    g = m.groupdict()
    release = [int(x) for x in g["release"].split(".")]
    while len(release) > 1 and release[-1] == 0:          # 1.0 == 1.0.0
        release.pop()
    return (int(g["epoch"] or 0), tuple(release),
            (_PRE[g["pre_l"]], int(g["pre_n"] or 0)) if g["pre_l"] else None,
            int(g["post_n1"] or g["post_n2"] or 0) if g["post"] else None,
            int(g["dev_n"] or 0) if g["dev"] else None,
            re.sub(r"[-_]", ".", g["local"]) if g["local"] else None)


def release_tag(version: str, tags) -> str | None:
    """The tag among tags (names, without refs/tags/) whose PEP 440 normalized version equals version's: the release tag
    is v<pyproject version> as written (e.g. v1.0.0-preview), the installed version its normalized form (1.0.0rc0)."""
    key = version_key(version)
    if key is None:
        return None
    hits = sorted(t for t in tags if version_key(t) == key)
    return next((t for t in hits if t == f"v{version}"), hits[0] if hits else None)


def cached_clone(d: Path) -> Path:
    """`git clone --depth 1` of the release tag of version d.name (the tag whose PEP 440 normalized version equals it,
    release_tag; main when there is no such tag) into d, once; SystemExit(2) on failure."""
    try:
        r = subprocess.run(["git", "ls-remote", "--tags", REPO_URL], capture_output=True, text=True)
    except FileNotFoundError:
        print("efe: the tasks need git (no clone here, no EFE_ROOT)", file=sys.stderr); raise SystemExit(2)
    if r.returncode:
        print(f"efe: cannot reach {REPO_URL} (git ls-remote exit {r.returncode}); clone it and run from there, or set "
              "EFE_ROOT", file=sys.stderr); raise SystemExit(2)
    tags = {ln.split("refs/tags/", 1)[1].removesuffix("^{}") for ln in r.stdout.splitlines() if "refs/tags/" in ln}
    tag = "main" if d.name == "main" else release_tag(d.name, tags)
    if tag is None:
        print(f"efe: {REPO_URL} has no release tag for version {d.name}: using main instead (delete {d} to clone again "
              "later)", file=sys.stderr)
        tag = "main"
    print(f"efe: no clone here and no EFE_ROOT: cloning the tasks ({tag}) into {d}, once", file=sys.stderr)
    d.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=f".{d.name}-", dir=d.parent)
    try:
        if subprocess.run(["git", "clone", "--depth", "1", "--branch", tag, REPO_URL, tmp]).returncode:
            print(f"efe: git clone of {tag} failed", file=sys.stderr); raise SystemExit(2)
        if not is_tree(d):                                  # else another run made it meanwhile
            try:
                os.rename(tmp, d)
            except OSError as e:
                print(f"efe: cannot place the clone at {d} ({e}); remove {d} and run again", file=sys.stderr)
                raise SystemExit(2)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return d


def find_root(clone: bool = True) -> Path | None:
    """The task tree: $EFE_ROOT; else the checkout that contains the working directory; else the checkout this file is in
    (`uv tool install -e .`); else the cached clone (made here on first use when clone; None when not)."""
    if _ROOT:
        return _ROOT[0]
    cwd = Path.cwd().resolve()
    if os.environ.get("EFE_ROOT"):
        d = Path(os.environ["EFE_ROOT"]).expanduser().resolve()
        if not is_tree(d):
            print(f"EFE_ROOT={d}: not a checkout of {REPO_URL}", file=sys.stderr); raise SystemExit(2)
    else:
        d = next((p for p in (cwd, *cwd.parents, Path(__file__).resolve().parents[1], cache_dir()) if is_tree(p)), None)
        if d is None and clone:
            d = cached_clone(cache_dir())
    if d is not None:
        _ROOT.append(d)
    return d


class _Scripts:
    """The task tree's own scripts/<name>.py (task_conventions, stamp_mtimes), imported on first use."""
    def __init__(self, name: str):
        self._name = name

    def __getattr__(self, attr: str):
        import importlib
        d = str(find_root() / "scripts")
        if d not in sys.path:
            sys.path.insert(0, d)
        return getattr(importlib.import_module(self._name), attr)


tc = _Scripts("task_conventions")
# ------------------------------------------------------------------------------------------------------------------------

MODES = {"--privileged": "privileged", "--privilege": "privileged", "--standard": "standard",
         "--realtime": "realtime"}
DATASET = ("game-exam", "efe")
SOURCES = ("-p", "--path", "-d", "--dataset", "-t", "--task", "-c", "--config", "--task-git-url")


def qualified(ref: str) -> str:
    """A Docker Hub short name with its registry: alpine:3 -> docker.io/library/alpine:3, a/b -> docker.io/a/b; a ref
    that names its registry (a first component with a dot or a port, or localhost) is unchanged."""
    name = ref.split("@", 1)[0]
    first, slash, _ = name.partition("/")
    if slash and ("." in first or ":" in first or first == "localhost"):
        return ref
    return ("docker.io/" if slash else "docker.io/library/") + ref


def engine_of(argv: list[str]) -> str | None:
    """The container engine of a `harbor run` command line: docker (no -e, or -e docker), podman (-e podman), None for
    any other environment (a cloud sandbox, a custom class)."""
    env, it = "docker", iter(argv)
    for a in it:
        if a in ("-e", "--env"):
            env = next(it, "")
        elif a.startswith("--env="):
            env = a.split("=", 1)[1]
    return env if env in ("docker", "podman") else None


def short_name_images(engine: str) -> list[str]:
    """The images Harbor 0.23 pulls by a short name before a trial whose task restricts egress (`network_mode =
    "allowlist"`, every task's default): the kernel probe's alpine (docker and podman: `container run` with a 30 s timeout,
    and a slow pull is taken for "allowlist unsupported" for the whole job) and, on podman, the egress sidecar's base
    image (its Dockerfile's FROM; podman's enforcing short-name mode refuses a short name without a terminal, unless the
    image is already in its store). Read from the installed Harbor; [] if it has neither."""
    try:
        from harbor.environments.docker import EGRESS_CONTROL_SIDECAR_CONTEXT_PATH as ctx
        from harbor.environments.docker.docker import DockerEnvironment
    except Exception:
        return []
    refs = [r for r in [getattr(DockerEnvironment, "_EGRESS_CONTROL_KERNEL_PROBE_IMAGE", None)] if r]
    if engine == "podman":
        try:
            lines = (Path(ctx) / "Dockerfile").read_text().splitlines()
        except OSError:
            lines = []
        for ln in lines:
            w = [x for x in ln.split() if not x.startswith("--")]   # FROM [--platform=...] <image> [AS <stage>]
            if len(w) > 1 and w[0].upper() == "FROM" and w[1] != "scratch" and "$" not in w[1]:
                refs.append(w[1])
    return [qualified(r) for r in refs]


def prepull(engine: str | None, refs: list[str] | None = None, run=subprocess.run) -> list[str]:
    """Pull each of `refs` (default: short_name_images(engine)) that the engine does not have, by its full name, quietly
    (one line per pull). Returns the refs it could not pull; Harbor then reports its own error."""
    if engine is None or not shutil.which(engine):
        return []
    failed = []
    for ref in short_name_images(engine) if refs is None else refs:
        try:
            if run([engine, "image", "inspect", ref], capture_output=True, timeout=60).returncode == 0:
                continue
            print(f"pulling {ref} (Harbor's egress allowlist)", file=sys.stderr)
            if run([engine, "pull", "-q", ref], capture_output=True, timeout=900, stdin=subprocess.DEVNULL).returncode:
                failed.append(ref)
        except (OSError, subprocess.SubprocessError):
            failed.append(ref)
    for ref in failed:
        print(f"could not pull {ref} (`{engine} pull {ref}` tells why)", file=sys.stderr)
    return failed


def harbor(args: list[str], app=None) -> int:
    if app is None:
        from harbor.cli import main as hm
        app = getattr(hm.app, "__wrapped_app__", hm.app)
    sys.argv = ["harbor", *args]
    return app() or 0


def bench_label(name: str) -> str | None:
    """A --benchmark value as its BENCHMARKS label: the label itself (any case) or its folder under tasks/."""
    by = {**{lab.lower(): lab for lab in tc.BENCHMARK_DIRS}, **{f: lab for lab, f in tc.BENCHMARK_DIRS.items()}}
    return by.get(name) or by.get(name.lower())


def under(paths: list[str]) -> set[str] | None:
    """The task dir names under the -p paths (a task dir, a benchmark folder, tasks/; a relative path that is not one
    here is taken in this clone, so `-p tasks/<benchmark>` works from anywhere); None: no -p given. SystemExit(2): a path
    that is neither."""
    if not paths:
        return None
    out: set[str] = set()
    for a in paths:
        d = Path(a).expanduser()
        if not d.is_dir() and not d.is_absolute() and (find_root() / d).is_dir():
            d = find_root() / d
        if not d.is_dir():
            print(f"-p {a}: no such directory (here or in {find_root()})", file=sys.stderr)
            raise SystemExit(2)
        d = d.resolve()
        if (d / "task.toml").is_file():
            out.add(d.name)
        else:
            out |= {t.parent.name for pat in ("*/task.toml", "*/*/task.toml") for t in d.glob(pat)}
    return out


def load_env() -> None:
    """The working directory's and the clone's .env (cp .env.example .env) into the environment: their non-empty keys
    the shell does not set (no clone is made for it)."""
    from dotenv import dotenv_values
    root = find_root(clone=False)
    for f in dict.fromkeys([Path.cwd() / ".env", *([root / ".env"] if root else [])]):
        for k, v in dotenv_values(f).items() if f.is_file() else ():
            if v and not v.startswith("#") and k not in os.environ:   # `KEY=   # note`: dotenv reads the note as the value
                os.environ[k] = v


def dataset_sets(argv: list[str]) -> list[str] | None:
    """argv with -d embodied-first-exam[@core|@all] turned into --core / --all; None: an unknown version."""
    out, it = [], iter(argv)
    for a in it:
        v = a.split("=", 1)[1] if a.startswith("--dataset=") else next(it, "") if a in ("-d", "--dataset") else None
        name, _, ver = (v or "").partition("@")
        if v is None or name not in DATASET:
            out += [a] if v is None or a.startswith("--dataset=") else [a, v]
        elif ver in ("", "core", "all"):
            out.append("--" + (ver or "core"))
        else:
            print(f"-d {v}: the versions are {name}@core and {name}@all", file=sys.stderr)
            return None
    return out


def run(argv: list[str], app=None) -> int:
    """`harbor run` with the set / mode / benchmark flags: picks the task dirs, then `harbor run -c <job config> ...`
    with a validated and staged frozen game selection."""
    argv = dataset_sets(argv)
    if argv is None:
        return 2
    load_env()
    ours = ("--core", "--all", "--benchmark", "--list", "--game-suite", "--family")
    if any(a in SOURCES or a.startswith(tuple(s + "=" for s in SOURCES if s.startswith("--"))) for a in argv):
        if not any(a in MODES or a in ours or a.startswith(("--benchmark=", "--game-suite=", "--family=")) for a in argv):
            if not {"-h", "--help"} & set(argv):
                prepull(engine_of(argv))
            return harbor(["run", *argv], app)                # the user's own task source: plain Harbor
    which, modes, benches, inc, exc, paths, listing, rest = "core", set(), [], [], [], [], False, []
    n_tasks = None
    game_suite, families = None, []
    it = iter(argv)
    for a in it:
        if a == "--game-suite" or a.startswith("--game-suite="):
            if game_suite is not None:
                print("select one --game-suite", file=sys.stderr); return 2
            game_suite = a.split("=", 1)[1] if "=" in a else next(it, "")
        elif a == "--family" or a.startswith("--family="):
            families.append(a.split("=", 1)[1] if "=" in a else next(it, ""))
        elif a in ("--all", "--core"):
            which = a[2:]
        elif a in MODES:
            modes.add(MODES[a])
        elif a == "--benchmark" or a.startswith("--benchmark="):
            b = a.split("=", 1)[1] if "=" in a else next(it, "")
            lab = bench_label(b)
            if lab is None:
                print(f"--benchmark {b!r}: not a benchmark (a README label or a folder under tasks/: "
                      f"{', '.join(sorted(tc.BENCHMARK_DIRS.values()))})", file=sys.stderr)
                return 2
            benches.append(lab)
        elif a in ("-i", "--include-task-name") or a.startswith("--include-task-name="):
            inc.append(a.split("=", 1)[1] if "=" in a else next(it, ""))
        elif a in ("-x", "--exclude-task-name") or a.startswith("--exclude-task-name="):
            exc.append(a.split("=", 1)[1] if "=" in a else next(it, ""))
        elif a in ("-l", "--n-tasks") or a.startswith("--n-tasks="):   # Harbor's -l: applied here, to the picked set
            v = a.split("=", 1)[1] if "=" in a else next(it, "")
            if not v.isdigit():
                print(f"{a} {v!r}: the number of tasks to run", file=sys.stderr); return 2
            n_tasks = int(v)
        elif a in ("-p", "--path") or a.startswith("--path="):
            paths.append(a.split("=", 1)[1] if "=" in a else next(it, ""))
        elif a in ("-c", "--config"):
            rest += [a, next(it, "")]                          # the user's config: layered after ours
        elif a in SOURCES or a.startswith(tuple(s + "=" for s in SOURCES if s.startswith("--") and s != "--config")):
            print(f"{a}: names its own tasks; it does not combine with {', '.join((*ours, *MODES))}", file=sys.stderr)
            return 2
        elif a == "--list":
            listing = True
        elif a in ("-h", "--help"):
            print(__doc__); return harbor(["run", "--help"], app)
        else:
            rest.append(a)
    if families and game_suite is None:
        print("--family requires --game-suite", file=sys.stderr); return 2
    if game_suite is not None and any(a in ("--core", "--all") for a in argv):
        print("--game-suite selects its own set; do not combine with --core/--all", file=sys.stderr); return 2
    games = _Scripts("prepare_games")
    if game_suite is None:
        game_suite = "all" if which == "all" else "core"
    if game_suite == "collab-overcooked":
        if modes or benches or paths or which != "core":
            print("Collab-Overcooked uses the native two-role protocol. Select recipes with --family or -i.", file=sys.stderr)
            return 2
        try:
            return _Scripts("collab_overcooked").launch(
                find_root(), families, inc, exc, n_tasks, listing, rest, lambda args: harbor(args, app))
        except (ValueError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if game_suite is not None:
        try:
            suite, plans = games.load_suite(game_suite)
            selected = games.select_tasks(suite, families=families)
        except (ValueError, OSError) as e:
            print(str(e), file=sys.stderr); return 2
        tasks = [row["name"] for row in selected]
    else:
        tasks = [t.name for t in tc.iter_tasks()]
    missing: dict[str, list[str]] = {}
    pick = tasks if game_suite is not None or which == "all" else sorted(set(tc.core_tasks(modes, missing=missing)) & set(tasks))
    for m, ts in sorted(missing.items()):
        print(f"{len(ts)} core task(s) have no {m} mode: skipped", file=sys.stderr)
    scope = under(paths)
    pick = [t for t in pick if (scope is None or t in scope)
            and (not modes or tc.mode_of(Path(t)) in modes)
            and (not benches or tc.bench_of(Path(t)) in benches)
            and (not inc or any(fnmatch.fnmatchcase(t, p) for p in inc))
            and not any(fnmatch.fnmatchcase(t, p) for p in exc)]
    pick = pick[:n_tasks] if n_tasks is not None else pick
    if not pick:
        print("no task matches", file=sys.stderr); return 2
    print(f"{len(pick)} task(s) of " + (game_suite if game_suite is not None else which) + (f", {', '.join(sorted(modes))}" if modes else "")
          + (f", {', '.join(sorted(set(benches)))}" if benches else ""), file=sys.stderr)
    if listing:
        print("\n".join(pick)); return 0
    if game_suite is not None:
        # Only task preparation differs. Native Harbor still layers configs, resolves agents and runs the job.
        # Keep these copies: lock.json refers to their paths for later verification.
        import uuid
        prepull(engine_of(rest))
        output = find_root() / "jobs/prepared" / f"games-{uuid.uuid4().hex}.json"
        cfg = games.prepare(suite, plans, [row for row in selected if row["name"] in pick], output)
        return harbor(["run", "-c", str(cfg), *rest], app)


def main() -> int:
    """The `efe` command: `efe run ...` = `harbor run ...` above, `efe` alone prints this help."""
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.replace("harbor run", "efe run")); return 0
    return run(argv[1:]) if argv[0] == "run" else harbor(argv)


if __name__ == "__main__":
    sys.exit(main())
