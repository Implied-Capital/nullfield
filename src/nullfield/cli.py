"""The nullfield CLI. Metadata commands emit JSON; context emits a Markdown index."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from . import __version__
from .experiments import run_experiment
from .integration import install_skill
from .store import (ResearchError, Store, add_entry, context, create_study,
                    get_record, list_records, search)


def positive(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Expected a positive integer") from None
    if number <= 0:
        raise argparse.ArgumentTypeError("Expected a positive integer")
    return number


def scope_flags(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--project", help="Registered project alias or UUID")
    group.add_argument("--session", help="Research-session UUID returned by session start")


def text_flags(parser: argparse.ArgumentParser, label: str = "body") -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(f"--{label}", dest="text", help=f"{label.capitalize()} text")
    group.add_argument("--file", type=Path, help="UTF-8 Markdown file; - reads stdin")


def body(args) -> str:
    if args.text is not None:
        return args.text
    return sys.stdin.read() if str(args.file) == "-" else args.file.read_text(encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="nullfield", description="Shared research projects and notebooks for Codex and Claude Code.")
    root.add_argument("--version", action="version", version=f"nullfield {__version__}")
    root.add_argument("--home", type=Path, help="Local registry directory (default: NULLFIELD_HOME or ~/.nullfield)")
    commands = root.add_subparsers(dest="command", required=True)

    projects = commands.add_parser("project", help="Create or register independent research projects").add_subparsers(dest="action", required=True)
    create = projects.add_parser("create")
    create.add_argument("alias")
    create.add_argument("--name", required=True)
    create.add_argument("--objective", required=True)
    create.add_argument("--path", type=Path, help="New or empty notebook directory; defaults to the local registry's projects directory")
    register = projects.add_parser("register")
    register.add_argument("alias")
    register.add_argument("path", type=Path)
    projects.add_parser("list")
    show = projects.add_parser("show")
    show.add_argument("project")

    resources = commands.add_parser("resource", help="Bind local resources to a project").add_subparsers(dest="action", required=True)
    resource = resources.add_parser("add")
    scope_flags(resource)
    resource.add_argument("name")
    resource.add_argument("location")
    resource.add_argument("--kind", choices=("repo", "dataset", "directory", "reference"), default="directory")
    resource.add_argument("--description", default="")
    scope_flags(resources.add_parser("list"))

    sessions = commands.add_parser("session", help="Create explicit, independent project bindings").add_subparsers(dest="action", required=True)
    start = sessions.add_parser("start")
    start.add_argument("project")
    start.add_argument("--agent", choices=("codex", "claude", "manual"), default="manual")
    listing = sessions.add_parser("list")
    listing.add_argument("--project")
    inspect = sessions.add_parser("show")
    inspect.add_argument("id")

    overview = commands.add_parser("context", help="Read a project's brief and recent record index")
    scope_flags(overview)
    overview.add_argument("--limit", type=positive, default=10)
    lookup = commands.add_parser("search", help="Search entry text and study plans; every word must match")
    scope_flags(lookup)
    lookup.add_argument("query")
    lookup.add_argument("--limit", type=positive, default=20)

    studies = commands.add_parser("study", help="Create bounded investigations").add_subparsers(dest="action", required=True)
    study = studies.add_parser("create")
    scope_flags(study)
    study.add_argument("--title", required=True)
    text_flags(study, "plan")
    scope_flags(studies.add_parser("list"))
    read = studies.add_parser("read")
    scope_flags(read)
    read.add_argument("id")

    entries = commands.add_parser("entry", help="Record findings, decisions, observations, and questions").add_subparsers(dest="action", required=True)
    entry = entries.add_parser("add")
    scope_flags(entry)
    entry.add_argument("--kind", choices=("finding", "decision", "observation", "question"), required=True)
    entry.add_argument("--title", required=True)
    text_flags(entry)
    entry.add_argument("--study")
    entry.add_argument("--evidence", action="append", default=[], help="Repeatable: run:UUID, entry:UUID, URL, or file")
    scope_flags(entries.add_parser("list"))
    read = entries.add_parser("read")
    scope_flags(read)
    read.add_argument("id")

    runs = commands.add_parser("run", help="Execute and record experiment commands").add_subparsers(dest="action", required=True)
    run = runs.add_parser("start")
    scope_flags(run)
    run.add_argument("--study", required=True)
    run.add_argument("--cwd", type=Path, required=True, help="Explicit experiment working directory")
    run.add_argument("--timeout", type=positive, default=300)
    run.add_argument("--input", action="append", default=[], help="File to hash before execution; relative to --cwd")
    run.add_argument("argv", nargs=argparse.REMAINDER, help="Command and arguments after --; no implicit shell")
    scope_flags(runs.add_parser("list"))
    read = runs.add_parser("read")
    scope_flags(read)
    read.add_argument("id")

    skills = commands.add_parser("skills", help="Install the packaged research skill").add_subparsers(dest="action", required=True)
    install = skills.add_parser("install")
    install.add_argument("--agent", choices=("codex", "claude", "both"), required=True)
    install.add_argument("--target", type=Path, help="Override the host's skills parent directory")
    install.add_argument("--force", action="store_true", help="Replace locally modified files from the packaged research skill")
    return root


def dispatch(store: Store, args):
    if args.command == "project":
        if args.action == "create":
            return store.create_project(args.alias, args.name, args.path, args.objective)
        if args.action == "register":
            return store.register_project(args.alias, args.path)
        if args.action == "list":
            return store.list_projects()
        return store.project(args.project)
    if args.command == "session":
        if args.action == "start":
            return store.start_session(store.project(args.project), args.agent)
        if args.action == "show":
            return store.session(args.id)
        return store.list_sessions(store.project(args.project) if args.project else None)
    project = store.scope(args.project, args.session)
    if args.command == "resource":
        if args.action == "add":
            return store.add_resource(project, args.name, args.location, args.kind, args.description)
        return store.resources(project)
    if args.command == "context":
        return context(store, project, args.session, args.limit)
    if args.command == "search":
        return search(project, args.query, args.limit)
    if args.command == "study" and args.action == "create":
        return create_study(project, args.title, body(args))
    if args.command == "entry" and args.action == "add":
        return add_entry(project, args.kind, args.title, body(args), args.study, args.evidence)
    if args.command == "run" and args.action == "start":
        argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
        return run_experiment(project, args.study, argv, args.cwd, args.timeout, args.input, store.resources(project))
    collection = {"study": "studies", "entry": "entries", "run": "runs"}[args.command]
    if args.action == "list":
        return list_records(project, collection)
    record = get_record(project, collection, args.id)
    if args.command != "run":
        filename = "plan.md" if args.command == "study" else "note.md"
        record["body"] = (Path(record["path"]) / filename).read_text(encoding="utf-8")
    return record


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    store = None
    try:
        if args.command == "skills":
            result = {"installed": install_skill(args.agent, args.target, args.force)}
        else:
            store = Store(args.home)
            result = dispatch(store, args)
        if isinstance(result, str):
            print(result, end="")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        if args.command == "run" and args.action == "start":
            code = result["returncode"]
            return code if code >= 0 else 128 - code
        return 0
    except (ResearchError, OSError, sqlite3.Error, subprocess.TimeoutExpired) as exc:
        print(f"nullfield: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("nullfield: interrupted", file=sys.stderr)
        return 130
    finally:
        if store:
            store.close()
