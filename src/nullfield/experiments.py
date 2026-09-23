"""Capture a command's evidence without implementing an agent execution loop."""

from __future__ import annotations

import hashlib
import os
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
    # Diff against HEAD includes both staged and unstaged tracked edits.
    patch = git("diff", "--binary", "HEAD") if not head.returncode else git("diff", "--binary", "--cached")
    if patch.returncode:
        raise ResearchError(f"Cannot capture Git state in {cwd}: {patch.stderr.decode(errors='replace')}")
    destination.write_bytes(patch.stdout)
    status = git("status", "--porcelain=v1", "--untracked-files=normal")
    if status.returncode:
        raise ResearchError(f"Cannot inspect Git working tree: {cwd}")
    return {"root": root.stdout.decode().strip(), "commit": head.stdout.decode().strip() if not head.returncode else None,
            "status": status.stdout.decode(errors="replace"), "tracked_patch": destination.name,
            "untracked_contents_captured": False}


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


def run_experiment(project: dict, study_id: str, command: list[str], cwd: Path | str,
                   timeout: int, inputs: list[str], resources: list[dict],
                   samples: list[tuple[str, str]] = (), acknowledge: bool = False,
                   detach: bool = False) -> dict:
    path = prepare_run(project, study_id, command, cwd, timeout, inputs, resources, samples, acknowledge)
    record = launch_supervisor(path) if detach else execute(path)
    return {**record, "path": str(path)}


def prepare_run(project: dict, study_id: str, command: list[str], cwd: Path | str,
                timeout: int, inputs: list[str], resources: list[dict],
                samples: list[tuple[str, str]], acknowledge: bool) -> Path:
    """Validate, capture provenance, and write a running record; nothing is launched yet."""
    if not command:
        raise ResearchError("Supply a command after --.")
    if timeout <= 0:
        raise ResearchError("Timeout must be positive.")
    study = get_record(project, "studies", study_id)
    # Check the ledger before any record exists: a refused run leaves no trace.
    started_on = today()
    planned_uses = check_uses(project, list(samples), study_id, started_on, acknowledge)
    cwd = Path(cwd).expanduser().resolve()
    if not cwd.is_dir():
        raise ResearchError(f"Working directory does not exist: {cwd}")
    fingerprints = []
    for value in inputs:
        path = Path(value).expanduser()
        path = (cwd / path).resolve() if not path.is_absolute() else path.resolve()
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
              "returncode": None, "finished_at": None, "runner_pid": None}
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
