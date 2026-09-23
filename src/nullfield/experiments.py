"""Capture a command's evidence without implementing an agent execution loop."""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
from pathlib import Path

from .ledger import check_uses, today, write_use
from .store import ResearchError, get_record, new_id, now, record_path, write_json


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
                   samples: list[tuple[str, str]] = (), acknowledge: bool = False) -> dict:
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
              "returncode": None, "finished_at": None}
    # Uses are recorded before launch: a command that starts may read outcomes even if it fails.
    record["sample_uses"] = [write_use(project, sample, purpose, study_id, run_id, started_on, "", reasons)["id"]
                             for sample, purpose, reasons in planned_uses]
    write_json(path / "record.json", record)
    with (path / "stdout.log").open("wb") as stdout, (path / "stderr.log").open("wb") as stderr:
        try:
            process = subprocess.Popen(command, cwd=cwd, stdout=stdout, stderr=stderr, start_new_session=os.name == "posix")
        except OSError as exc:
            record.update(status="failed", returncode=127, error=str(exc))
        else:
            record["pid"] = process.pid
            write_json(path / "record.json", record)
            try:
                returncode = process.wait(timeout=timeout)
                record.update(status="completed" if returncode == 0 else "failed", returncode=returncode)
            except subprocess.TimeoutExpired:
                terminate(process)
                record.update(status="timed_out", returncode=124)
            except KeyboardInterrupt:
                terminate(process)
                record.update(status="interrupted", returncode=130)
    record["finished_at"] = now()
    write_json(path / "record.json", record)
    return {**record, "path": str(path)}
