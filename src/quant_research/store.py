"""Portable project files, with machine-local registration in SQLite."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


class ResearchError(Exception):
    """An actionable user-facing error."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def checked_id(value: str) -> str:
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError, TypeError):
        raise ResearchError(f"Invalid ID: {value}") from None
    return value


def alias_name(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise ResearchError("Names must be 1–64 lowercase letters, numbers, hyphens or underscores.")
    try:
        uuid.UUID(value)
    except ValueError:
        pass
    else:
        raise ResearchError("UUIDs are reserved for record identities; choose a descriptive name.")
    return value


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ResearchError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ResearchError(f"Expected a JSON object in {path}")
    return value


def atomic_text(path: Path, text: str) -> None:
    """Replace one file atomically; each notebook record has its own unique path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".qr-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_json(path: Path, data: dict) -> None:
    atomic_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


class Store:
    def __init__(self, home: Path | str | None = None):
        self.home = Path(home or os.environ.get("QR_HOME", "~/.quant-research")).expanduser().resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.home / "registry.sqlite3", timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY, alias TEXT UNIQUE NOT NULL, path TEXT UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS resources (
                project_id TEXT NOT NULL REFERENCES projects(id),
                name TEXT NOT NULL, kind TEXT NOT NULL, location TEXT NOT NULL,
                description TEXT NOT NULL, PRIMARY KEY(project_id, name)
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                agent TEXT NOT NULL, created_at TEXT NOT NULL
            );
        """)

    def close(self) -> None:
        self.db.close()

    def create_project(self, alias: str, name: str, root: Path | str | None, objective: str) -> dict:
        alias_name(alias)
        if not name.strip() or not objective.strip():
            raise ResearchError("A project needs a name and an objective.")
        root = Path(root or self.home / "projects" / alias).expanduser().resolve()
        # Reserve the registry alias before touching the destination. SQLite serializes creates.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if self.db.execute("SELECT 1 FROM projects WHERE alias = ?", (alias,)).fetchone():
                raise ResearchError(f"Project alias already exists: {alias}")
            if root.exists() and (not root.is_dir() or any(root.iterdir())):
                raise ResearchError(f"Project directory must be new or empty: {root}")
            root.mkdir(parents=True, exist_ok=True)
            manifest = {"schema_version": 1, "id": new_id(), "name": name, "created_at": now()}
            atomic_text(root / "brief.md", f"# {name}\n\n{objective.strip()}\n")
            write_json(root / "project.json", manifest)
            self.db.execute("INSERT INTO projects VALUES (?, ?, ?)", (manifest["id"], alias, str(root)))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.project(alias)

    def register_project(self, alias: str, root: Path | str) -> dict:
        alias_name(alias)
        root = Path(root).expanduser().resolve()
        manifest = self._manifest(root)
        with self.db:
            existing = self.db.execute("SELECT * FROM projects WHERE id = ?", (manifest["id"],)).fetchone()
            try:
                if existing:
                    self.db.execute("UPDATE projects SET alias = ?, path = ? WHERE id = ?", (alias, str(root), manifest["id"]))
                else:
                    self.db.execute("INSERT INTO projects VALUES (?, ?, ?)", (manifest["id"], alias, str(root)))
            except sqlite3.IntegrityError:
                raise ResearchError("That alias or directory is registered to another project.") from None
        return self.project(alias)

    @staticmethod
    def _manifest(root: Path) -> dict:
        data = read_json(root / "project.json")
        if data.get("schema_version") != 1 or not isinstance(data.get("name"), str) or not data["name"].strip():
            raise ResearchError(f"Unsupported or invalid project manifest: {root}")
        checked_id(data.get("id", ""))
        if not (root / "brief.md").is_file():
            raise ResearchError(f"Missing research brief: {root / 'brief.md'}")
        return data

    def project(self, selector: str) -> dict:
        row = self.db.execute("SELECT * FROM projects WHERE alias = ? OR id = ?", (selector, selector)).fetchone()
        if not row:
            raise ResearchError(f"Unknown project: {selector}. Use 'qr project list' or 'qr project register'.")
        data = self._manifest(Path(row["path"]))
        if data["id"] != row["id"]:
            raise ResearchError("Project identity changed on disk. Register the correct project directory.")
        return {**data, "alias": row["alias"], "path": row["path"]}

    def list_projects(self) -> list[dict]:
        # Listing remains possible when a registered drive or directory is unavailable.
        return [dict(row) for row in self.db.execute("SELECT * FROM projects ORDER BY alias")]

    def add_resource(self, project: dict, name: str, location: str, kind: str, description: str) -> dict:
        alias_name(name)
        if kind == "reference" and location.startswith(("https://", "http://")):
            resolved = location
        else:
            path = Path(location).expanduser().resolve()
            if not path.exists():
                raise ResearchError(f"Resource does not exist: {path}")
            if kind in ("repo", "directory") and not path.is_dir():
                raise ResearchError(f"Expected a directory: {path}")
            resolved = str(path)
        with self.db:
            self.db.execute("""INSERT INTO resources VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_id, name) DO UPDATE SET
                kind=excluded.kind, location=excluded.location, description=excluded.description""",
                (project["id"], name, kind, resolved, description))
        return {"project_id": project["id"], "name": name, "kind": kind, "location": resolved, "description": description}

    def resources(self, project: dict) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM resources WHERE project_id = ? ORDER BY name", (project["id"],))]

    def start_session(self, project: dict, agent: str) -> dict:
        session = {"id": new_id(), "project_id": project["id"], "agent": agent, "created_at": now()}
        with self.db:
            self.db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)", tuple(session.values()))
        return {**session, "project_alias": project["alias"], "project_path": project["path"]}

    def session(self, session_id: str) -> dict:
        checked_id(session_id)
        row = self.db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            raise ResearchError(f"Unknown research session: {session_id}")
        return dict(row)

    def list_sessions(self, project: dict | None = None) -> list[dict]:
        query = "SELECT sessions.*, projects.alias AS project_alias FROM sessions JOIN projects ON project_id = projects.id"
        params = ()
        if project:
            query += " WHERE project_id = ?"
            params = (project["id"],)
        return [dict(r) for r in self.db.execute(query + " ORDER BY created_at DESC", params)]

    def scope(self, project: str | None, session: str | None) -> dict:
        if bool(project) == bool(session):
            raise ResearchError("Specify exactly one of --project or --session.")
        return self.project(project if project else self.session(session)["project_id"])


def record_path(project: dict, collection: str, record_id: str) -> Path:
    return Path(project["path"]) / collection / checked_id(record_id)


def get_record(project: dict, collection: str, record_id: str) -> dict:
    path = record_path(project, collection, record_id)
    record = read_json(path / "record.json")
    if record.get("project_id") != project["id"] or record.get("id") != record_id:
        raise ResearchError(f"Record does not belong to the selected project: {record_id}")
    return {**record, "path": str(path)}


def list_records(project: dict, collection: str) -> list[dict]:
    directory = Path(project["path"]) / collection
    records = [get_record(project, collection, p.parent.name) for p in directory.glob("*/record.json")]
    return sorted(records, key=lambda r: (r["created_at"], r["id"]), reverse=True)


def create_study(project: dict, title: str, plan: str) -> dict:
    if not title.strip() or not plan.strip():
        raise ResearchError("A study needs a title and an experiment plan.")
    record = {"id": new_id(), "project_id": project["id"], "title": title, "created_at": now()}
    path = record_path(project, "studies", record["id"])
    atomic_text(path / "plan.md", plan.strip() + "\n")
    # Metadata is published last so readers do not see half-written records.
    write_json(path / "record.json", record)
    return {**record, "path": str(path)}


def add_entry(project: dict, kind: str, title: str, body: str, study_id: str | None, evidence: list[str]) -> dict:
    if not title.strip() or not body.strip():
        raise ResearchError("An entry needs a title and a body.")
    if study_id:
        get_record(project, "studies", study_id)
    if kind == "finding" and not evidence:
        raise ResearchError("A finding needs --evidence (a run ID, entry ID, URL, or existing file).")
    resolved = []
    for ref in evidence:
        if ref.startswith("run:"):
            run = get_record(project, "runs", ref[4:])
            if run["status"] == "running":
                raise ResearchError("A running experiment is not completed evidence.")
            resolved.append(ref)
        elif ref.startswith("entry:"):
            get_record(project, "entries", ref[6:])
            resolved.append(ref)
        elif ref.startswith(("https://", "http://")):
            resolved.append(ref)
        else:
            path = Path(ref).expanduser().resolve()
            if not path.is_file():
                raise ResearchError(f"Evidence file does not exist: {path}")
            resolved.append(str(path))
    record = {"id": new_id(), "project_id": project["id"], "kind": kind, "title": title,
              "created_at": now(), "study_id": study_id, "evidence": resolved}
    path = record_path(project, "entries", record["id"])
    atomic_text(path / "note.md", f"# {title}\n\n{body.strip()}\n")
    write_json(path / "record.json", record)
    return {**record, "path": str(path)}


def search(project: dict, query: str, limit: int = 20) -> list[dict]:
    terms = query.casefold().split()
    if not terms:
        raise ResearchError("Search needs at least one word.")
    matches = []
    for collection, filename in (("entries", "note.md"), ("studies", "plan.md")):
        for record in list_records(project, collection):
            body = (Path(record["path"]) / filename).read_text(encoding="utf-8")
            text = record["title"] + "\n" + body
            if all(term in text.casefold() for term in terms):
                line = next((line for line in body.splitlines() if any(t in line.casefold() for t in terms)), "")
                matches.append({**record, "collection": collection, "excerpt": line[:400]})
    return sorted(matches, key=lambda r: r["created_at"], reverse=True)[:limit]


def context(store: Store, project: dict, session_id: str | None, limit: int = 10) -> str:
    lines = [f"# Research project: {project['name']}", f"Project ID: {project['id']}",
             f"Alias: {project['alias']}", f"Notebook: {project['path']}",
             f"Research session: {session_id or '(explicit project selection)'}", "",
             "## Brief", (Path(project["path"]) / "brief.md").read_text(encoding="utf-8").strip(),
             "", "## Local resources"]
    for resource in store.resources(project):
        lines.append(f"- {resource['name']} ({resource['kind']}): {resource['location']} — {resource['description']}")
    for collection in ("studies", "entries", "runs"):
        records = list_records(project, collection)
        lines.extend(["", f"## Recent {collection} ({min(limit, len(records))} of {len(records)})"])
        for record in records[:limit]:
            label = record.get("title") or " ".join(record["command"])
            status = record.get("kind") or record.get("status", "study")
            lines.append(f"- {record['id']} [{status}] {label} — {record['path']}")
    lines.extend(["", "This is an index, not the complete evidence. Search related studies and entries,",
                  "including negative results, and open the underlying records before continuing."])
    return "\n".join(lines) + "\n"
