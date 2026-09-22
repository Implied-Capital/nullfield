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
    content = files("quant_research").joinpath("skills/research/SKILL.md").read_text(encoding="utf-8")
    command = shlex.join([sys.executable, "-m", "quant_research"])
    content = content.replace(
        "# Research\n",
        "# Research\n\n## Installed CLI\n\n"
        f"Use `{command}` in place of `qr` in the examples below. This absolute\n"
        "command works even when the host did not inherit the installation's PATH.\n",
        1,
    )
    destinations = []
    for host in agents:
        base = Path(target).expanduser() if target else Path.home() / (".agents/skills" if host == "codex" else ".claude/skills")
        destination = base.resolve() / "research" / "SKILL.md"
        if destination.exists() and destination.read_text(encoding="utf-8") != content and not force:
            raise ResearchError(f"A different skill already exists at {destination}. Use --force to replace that file.")
        destinations.append(destination)
    for destination in destinations:
        atomic_text(destination, content)
    return [str(p) for p in destinations]
