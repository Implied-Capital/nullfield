"""Install the same portable research skill into either host."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
import shlex
import sys

from .store import ResearchError, atomic_text


def install_skill(agent: str, target: Path | str | None = None, force: bool = False) -> list[str]:
    if target and agent == "both":
        raise ResearchError("Use --target with a single agent, or install both into their default locations.")
    agents = ("codex", "claude") if agent == "both" else (agent,)
    source = files("nullfield").joinpath("skills/research")
    content = source.joinpath("SKILL.md").read_text(encoding="utf-8")
    command = shlex.join([sys.executable, "-m", "nullfield"])
    content = content.replace(
        "# Research\n",
        "# Research\n\n## Installed CLI\n\n"
        f"Use `{command}` in place of `nullfield` in the examples below. This absolute\n"
        "command works even when the host did not inherit the installation's PATH.\n",
        1,
    )
    bundle = {Path("SKILL.md"): content}
    for reference in sorted(source.joinpath("references").iterdir(), key=lambda p: p.name):
        if reference.is_file() and reference.name.endswith(".md"):
            bundle[Path("references") / reference.name] = reference.read_text(encoding="utf-8")
    destinations = []
    for host in agents:
        base = Path(target).expanduser() if target else Path.home() / (".agents/skills" if host == "codex" else ".claude/skills")
        for relative, text in bundle.items():
            destination = base.resolve() / "research" / relative
            if destination.exists() and destination.read_text(encoding="utf-8") != text and not force:
                raise ResearchError(f"A different skill file already exists at {destination}. Use --force to replace it.")
            destinations.append((destination, text))
    # Check every host and file before writing; publish the entrypoints last.
    for destination, content in sorted(destinations, key=lambda item: item[0].name == "SKILL.md"):
        atomic_text(destination, content)
    return [str(path) for path, _ in destinations]
