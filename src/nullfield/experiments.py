"""Capture a command's evidence without implementing an agent execution loop."""

from __future__ import annotations

import hashlib
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from .ledger import check_uses, today, write_use
from .store import ResearchError, get_record, new_id, now, read_json, record_path, write_json


def fingerprint(path: Path) -> dict:
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "sha256": digest, "bytes": path.stat().st_size}


def resolve(cwd: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return (cwd / path).resolve() if not path.is_absolute() else path.resolve()


def collect_outputs(run_dir: Path, record: dict) -> list[dict]:
    """Fingerprint every declared output file; copy files that fit the run's keep budget."""
    budget, cwd, results = record.get("output_keep_bytes", 0), Path(record["cwd"]), []
    for index, declared in enumerate(record.get("declared_outputs", [])):
        root = Path(declared)
        if not root.exists():
            results.append({"path": declared, "missing": True})
            continue
        files = [root] if root.is_file() else sorted(f for f in root.rglob("*") if f.is_file())
        for file in files[:MAX_OUTPUT_FILES]:
            entry = {**fingerprint(file), "kept": None}
            if entry["bytes"] <= budget:
                try:
                    relative = Path("outputs") / file.relative_to(cwd)
                except ValueError:
                    relative = Path("outputs") / f"external-{index:02d}" / file.relative_to(root.parent)
                (run_dir / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(file, run_dir / relative)
                budget -= entry["bytes"]
                entry["kept"] = str(relative)
            results.append(entry)
        if len(files) > MAX_OUTPUT_FILES:
            results.append({"path": declared, "files_not_recorded": len(files) - MAX_OUTPUT_FILES})
    return results


def summarize_stderr(path: Path, top: int = 5) -> dict:
    """Line counts, warnings, tracebacks, and the most repeated lines, for triage."""
    counts: dict[str, int] = {}
    lines = warnings = 0
    traceback = False
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            text = line.strip()
            lines += 1
            warnings += "Warning" in text
            traceback = traceback or text.startswith("Traceback (most recent call last)")
            if text:
                counts[text[:300]] = counts.get(text[:300], 0) + 1
    repeated = sorted(((n, text) for text, n in counts.items() if n > 1), reverse=True)[:top]
    return {"lines": lines, "warning_lines": warnings, "traceback": traceback,
            "most_repeated": [{"count": n, "line": text} for n, text in repeated]}


def git_snapshot(cwd: Path, destination: Path) -> dict | None:
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, timeout=30)

    try:
        root = git("rev-parse", "--show-toplevel")
    except FileNotFoundError:
        return None
    if root.returncode:
        return None
    head = git("rev-parse", "HEAD")
    # Diff against HEAD includes both staged and unstaged tracked edits. Text changes are
    # stored as a patch; binary changes are fingerprinted, since their bytes dominate size.
    base = ["HEAD"] if not head.returncode else ["--cached"]
    patch = git("diff", "--no-renames", *base)
    numstat = git("diff", "--no-renames", "--numstat", "-z", *base)
    if patch.returncode or numstat.returncode:
        error = (patch.stderr or numstat.stderr).decode(errors="replace")
        raise ResearchError(f"Cannot capture Git state in {cwd}: {error}")
    destination.write_bytes(patch.stdout)
    top = Path(root.stdout.decode().strip())
    binary = []
    for item in numstat.stdout.decode(errors="replace").split("\0"):
        added, _, rest = item.partition("\t")
        if added != "-":
            continue
        name = rest.partition("\t")[2]
        file = top / name
        binary.append({**fingerprint(file), "path": name} if file.is_file() else {"path": name, "deleted": True})
    status = git("status", "--porcelain=v1", "--untracked-files=normal")
    if status.returncode:
        raise ResearchError(f"Cannot inspect Git working tree: {cwd}")
    return {"root": root.stdout.decode().strip(), "commit": head.stdout.decode().strip() if not head.returncode else None,
            "status": status.stdout.decode(errors="replace"), "tracked_patch": destination.name,
            "binary_changes": binary, "untracked_contents_captured": False}


def terminate(process: subprocess.Popen) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    else:
        process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        if os.name != "posix":
            process.kill()
    # The leader can exit while a child ignores SIGTERM. Kill the remaining
    # group even when wait() already returned for the leader.
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()


DEFAULT_KEEP_BYTES = 5 * 1024 * 1024
MAX_OUTPUT_FILES = 10_000


def run_experiment(project: dict, study_id: str, command: list[str], cwd: Path | str,
                   timeout: int, inputs: list[str], resources: list[dict],
                   samples: list[tuple[str, str]] = (), acknowledge: bool = False,
                   detach: bool = False, outputs: list[str] = (), keep_bytes: int = DEFAULT_KEEP_BYTES) -> dict:
    path = prepare_run(project, study_id, command, cwd, timeout, inputs, resources, samples, acknowledge,
                       outputs, keep_bytes)
    record = launch_supervisor(path) if detach else execute(path)
    return {**record, "path": str(path)}


def prepare_run(project: dict, study_id: str, command: list[str], cwd: Path | str,
                timeout: int, inputs: list[str], resources: list[dict],
                samples: list[tuple[str, str]], acknowledge: bool,
                outputs: list[str] = (), keep_bytes: int = DEFAULT_KEEP_BYTES) -> Path:
    """Validate, capture provenance, and write a running record; nothing is launched yet."""
    if not command:
        raise ResearchError("Supply a command after --.")
    if timeout <= 0:
        raise ResearchError("Timeout must be positive.")
    study = get_record(project, "studies", study_id)
    study_id = study["id"]
    # Check the ledger before any record exists: a refused run leaves no trace.
    started_on = today()
    planned_uses = check_uses(project, list(samples), study_id, started_on, acknowledge)
    cwd = Path(cwd).expanduser().resolve()
    if not cwd.is_dir():
        raise ResearchError(f"Working directory does not exist: {cwd}")
    fingerprints = []
    for value in inputs:
        path = resolve(cwd, value)
        if not path.is_file():
            raise ResearchError(f"Input must be an existing file: {path}")
        fingerprints.append(fingerprint(path))
    run_id = new_id()
    path = record_path(project, "runs", run_id)
    path.mkdir(parents=True)
    plan = (Path(study["path"]) / "plan.md").read_bytes()
    (path / "plan.md").write_bytes(plan)
    code = []
    seen = set()
    candidates = [("cwd", cwd)] + [(r["name"], Path(r["location"])) for r in resources if r["kind"] == "repo"]
    for index, (label, directory) in enumerate(candidates):
        if not directory.is_dir():
            raise ResearchError(f"Repository resource is unavailable: {directory}")
        patch_path = path / f"code-{index:02d}.patch"
        snapshot = git_snapshot(directory, patch_path)
        if snapshot and snapshot["root"] not in seen:
            code.append({"resource": label, **snapshot})
            seen.add(snapshot["root"])
        else:
            patch_path.unlink(missing_ok=True)
    record = {"id": run_id, "project_id": project["id"], "study_id": study_id,
              "created_at": now(), "status": "running", "command": command, "cwd": str(cwd),
              "timeout_seconds": timeout, "inputs": fingerprints, "code": code,
              "plan_sha256": hashlib.sha256(plan).hexdigest(),
              "stdout": "stdout.log", "stderr": "stderr.log",
              "returncode": None, "finished_at": None, "runner_pid": None,
              "declared_outputs": [str(resolve(cwd, value)) for value in outputs],
              "output_keep_bytes": max(keep_bytes, 0)}
    # Uses are recorded before launch: a command that starts may read outcomes even if it fails.
    record["sample_uses"] = [write_use(project, sample, purpose, study_id, run_id, started_on, "", reasons)["id"]
                             for sample, purpose, reasons in planned_uses]
    write_json(path / "record.json", record)
    return path


def _raise_interrupt(signum, frame):
    raise KeyboardInterrupt


def execute(path: Path) -> dict:
    """Run a prepared command to completion and finalize its record. The caller becomes the runner."""
    record = read_json(path / "record.json")
    record["runner_pid"] = os.getpid()
    write_json(path / "record.json", record)
    # `run stop` signals the runner; turn SIGTERM into the interrupt path so the command is cleaned up.
    handler = None
    if threading.current_thread() is threading.main_thread():
        handler = signal.signal(signal.SIGTERM, _raise_interrupt)
    process = None
    try:
        with (path / "stdout.log").open("wb") as stdout, (path / "stderr.log").open("wb") as stderr:
            try:
                process = subprocess.Popen(record["command"], cwd=record["cwd"], stdout=stdout, stderr=stderr,
                                           start_new_session=os.name == "posix")
            except OSError as exc:
                record.update(status="failed", returncode=127, error=str(exc))
            else:
                record["pid"] = process.pid
                write_json(path / "record.json", record)
                returncode = process.wait(timeout=record["timeout_seconds"])
                record.update(status="completed" if returncode == 0 else "failed", returncode=returncode)
    except subprocess.TimeoutExpired:
        terminate(process)
        record.update(status="timed_out", returncode=124)
    except KeyboardInterrupt:
        if process is not None:
            terminate(process)
        if (path / STOP_MARKER).exists():
            record.update(status="stopped", returncode=143)
        else:
            record.update(status="interrupted", returncode=130)
    finally:
        if handler is not None:
            signal.signal(signal.SIGTERM, handler)
    # Evidence collection must never leave the record unfinished.
    for key, collect in (("outputs", lambda: collect_outputs(path, record)),
                         ("stderr_summary", lambda: summarize_stderr(path / "stderr.log"))):
        try:
            record[key] = collect()
        except OSError as exc:
            record[key] = {"error": str(exc)}
    record["finished_at"] = now()
    write_json(path / "record.json", record)
    return record


STOP_MARKER = "stop_requested"


def launch_supervisor(path: Path, startup_timeout: float = 30) -> dict:
    """Start a detached supervisor that executes the run, and return once it owns the record."""
    # The intermediate process exits immediately, leaving the supervisor outside the caller's children.
    subprocess.run([sys.executable, "-m", "nullfield.supervise", "--spawn", str(path)],
                   stdin=subprocess.DEVNULL, check=True, timeout=startup_timeout)
    deadline = time.monotonic() + startup_timeout
    while time.monotonic() < deadline:
        record = read_json(path / "record.json")
        if record.get("runner_pid") or record["status"] != "running":
            return {**record, "detached": True}
        time.sleep(0.05)
    record.update(status="failed", returncode=127, finished_at=now(),
                  error=f"Supervisor did not start the command; see {path / 'supervisor.log'}")
    write_json(path / "record.json", record)
    return {**record, "detached": True}


def alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def run_state(record: dict) -> str:
    """The recorded status, or 'lost' when a running record's runner has died without finishing it."""
    if record["status"] == "running" and record.get("runner_pid") and not alive(record["runner_pid"]):
        return "lost"
    return record["status"]


def wait_run(project: dict, run_id: str, timeout: float | None) -> dict:
    run_id = get_record(project, "runs", run_id)["id"]
    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        record = get_record(project, "runs", run_id)
        state = run_state(record)
        if state != "running" or (deadline is not None and time.monotonic() >= deadline):
            return {**record, "state": state}
        time.sleep(0.2)


def stop_run(project: dict, run_id: str, grace: float = 10) -> dict:
    record = get_record(project, "runs", run_id)
    state = run_state(record)
    if state != "running":
        raise ResearchError(f"Run is not running (state: {state}).")
    if not record.get("runner_pid"):
        raise ResearchError("Run has not started yet; retry in a moment.")
    (Path(record["path"]) / STOP_MARKER).write_text(now() + "\n")
    os.kill(record["runner_pid"], signal.SIGTERM)
    return wait_run(project, run_id, grace)
