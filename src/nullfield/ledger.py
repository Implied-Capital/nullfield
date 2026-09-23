"""Evaluation-data ledger: named samples and the durable history of their use.

A sample names evaluation data (a dataset, optionally bounded by dates). A use
records that a study or run saw that sample's outcomes, and for what purpose.
Uses are append-only notebook records: looking at data cannot be undone, so
neither can its record. Dated samples of the same dataset share history when
their date ranges intersect.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from .store import (ResearchError, alias_name, get_record, list_records, new_id, now,
                    plan_status, read_json, record_path, study_freezes, write_json)

ROLES = ("development", "holdout")
PURPOSES = ("fit", "select", "evaluate", "inspect")


def checked_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ResearchError(f"Expected a YYYY-MM-DD date: {value}") from None


def sample_path(project: dict, name: str) -> Path:
    return Path(project["path"]) / "samples" / alias_name(name)


def define_sample(project: dict, name: str, dataset: str, start: str | None, end: str | None,
                  role: str, description: str) -> dict:
    if role not in ROLES:
        raise ResearchError(f"Sample role must be one of: {', '.join(ROLES)}")
    if not dataset.strip():
        raise ResearchError("A sample needs a dataset name.")
    start, end = checked_date(start), checked_date(end)
    if start and end and start > end:
        raise ResearchError("A sample's start date must not follow its end date.")
    path = sample_path(project, name)
    try:
        # The directory reserves the name atomically; definitions are never rewritten
        # because recorded uses would silently change meaning.
        path.mkdir(parents=True)
    except FileExistsError:
        raise ResearchError(f"Sample already defined: {name}. Define a new name instead.") from None
    record = {"id": new_id(), "project_id": project["id"], "name": name, "dataset": dataset.strip(),
              "start": start, "end": end, "role": role, "description": description.strip(),
              "created_at": now()}
    write_json(path / "record.json", record)
    return {**record, "path": str(path)}


def get_sample(project: dict, name: str) -> dict:
    path = sample_path(project, name)
    if not (path / "record.json").is_file():
        raise ResearchError(f"Unknown sample: {name}. Use 'nullfield sample list'.")
    record = read_json(path / "record.json")
    if record.get("project_id") != project["id"] or record.get("name") != name:
        raise ResearchError(f"Sample does not belong to the selected project: {name}")
    return {**record, "path": str(path)}


def list_samples(project: dict) -> list[dict]:
    directory = Path(project["path"]) / "samples"
    return sorted((get_sample(project, p.parent.name) for p in directory.glob("*/record.json")),
                  key=lambda s: (s["dataset"], s["start"] or "", s["name"]))


def overlaps(a: dict, b: dict) -> bool:
    """Same dataset and intersecting dates; an undated sample only matches itself."""
    if a["name"] == b["name"]:
        return True
    if a["dataset"] != b["dataset"]:
        return False
    if not (a["start"] or a["end"]) or not (b["start"] or b["end"]):
        return False
    return (a["start"] or "0000") <= (b["end"] or "9999") and (b["start"] or "0000") <= (a["end"] or "9999")


def uses_of(project: dict, sample: dict, before: str | None = None) -> list[dict]:
    """Uses of this sample or an overlapping one, newest first, optionally on or before a date."""
    related = {s["name"] for s in list_samples(project) if overlaps(sample, s)}
    return [u for u in list_records(project, "uses")
            if u["sample"] in related and (before is None or u["occurred_on"] <= before)]


def conflicts(project: dict, sample: dict, purpose: str, study_id: str | None, occurred_on: str) -> list[str]:
    """Reasons this use would compromise a sample, or an empty list."""
    reasons = []
    if purpose != "evaluate":
        for other in list_samples(project):
            if other["role"] == "holdout" and overlaps(sample, other):
                via = "" if other["name"] == sample["name"] else f", which overlaps {sample['name']}"
                reasons.append(f"holdout sample {other['name']}{via}: using it to {purpose} spends it")
    else:
        reasons.extend(preregistration_gaps(project, sample, study_id, occurred_on))
        for use in uses_of(project, sample, before=occurred_on):
            # Repeating a study's own evaluation is visible in the ledger but is not prior use.
            if study_id and use["study_id"] == study_id and use["purpose"] == "evaluate":
                continue
            via = "" if use["sample"] == sample["name"] else f" via overlapping sample {use['sample']}"
            if use["study_id"]:
                who = f"study '{get_record(project, 'studies', use['study_id'])['title']}' ({use['study_id']})"
            else:
                who = f"no study ({use['note']})"
            reasons.append(f"prior use {use['id']}: {use['purpose']} on {use['occurred_on']} by {who}{via}")
    return reasons


def preregistration_gaps(project: dict, sample: dict, study_id: str | None, occurred_on: str) -> list[str]:
    """An evaluation touching a holdout needs a plan frozen by then, and unchanged since if the use is today."""
    holdouts = [s["name"] for s in list_samples(project) if s["role"] == "holdout" and overlaps(sample, s)]
    if not holdouts:
        return []
    touching = f"evaluating {sample['name']} (holdout: {', '.join(holdouts)})"
    if not study_id:
        return [f"{touching} without a study, so without a frozen plan"]
    study = get_record(project, "studies", study_id)
    frozen = [f for f in study_freezes(project, study_id) if f["created_at"][:10] <= occurred_on]
    if not frozen:
        return [f"{touching}: study '{study['title']}' had no frozen plan by {occurred_on}; "
                "run 'nullfield study freeze' first"]
    if occurred_on == today() and plan_status(project, study) == "drifted":
        return [f"{touching}: the plan changed after its last freeze; freeze an amendment first"]
    return []


def check_uses(project: dict, requests: list[tuple[str, str]], study_id: str | None,
               occurred_on: str, acknowledge: bool) -> list[tuple[dict, str, list[str]]]:
    """Validate every requested use before any is written."""
    checked = []
    for name, purpose in requests:
        if purpose not in PURPOSES:
            raise ResearchError(f"Purpose must be one of: {', '.join(PURPOSES)}")
        sample = get_sample(project, name)
        reasons = conflicts(project, sample, purpose, study_id, occurred_on)
        if reasons and not acknowledge:
            raise ResearchError(f"Recording {purpose} on sample {name} conflicts with the ledger:\n- "
                                + "\n- ".join(reasons)
                                + "\nNothing was recorded. If this use is intended, rerun with "
                                  "--acknowledge-conflicts and label the result as using previously seen data.")
        checked.append((sample, purpose, reasons))
    return checked


def write_use(project: dict, sample: dict, purpose: str, study_id: str | None, run_id: str | None,
              occurred_on: str, note: str, reasons: list[str]) -> dict:
    record = {"id": new_id(), "project_id": project["id"], "sample": sample["name"], "purpose": purpose,
              "study_id": study_id, "run_id": run_id, "occurred_on": occurred_on, "note": note.strip(),
              "acknowledged_conflicts": reasons, "created_at": now()}
    path = record_path(project, "uses", record["id"])
    write_json(path / "record.json", record)
    return {**record, "path": str(path)}


def record_use(project: dict, sample_name: str, purpose: str, study_id: str | None,
               occurred_on: str | None, note: str, acknowledge: bool) -> dict:
    if study_id:
        get_record(project, "studies", study_id)
    elif not note.strip():
        raise ResearchError("A use without --study needs a --note saying who used the data and why.")
    occurred_on = checked_date(occurred_on) or today()
    if occurred_on > today():
        raise ResearchError("A use cannot be recorded in the future.")
    [(sample, purpose, reasons)] = check_uses(project, [(sample_name, purpose)], study_id, occurred_on, acknowledge)
    return write_use(project, sample, purpose, study_id, None, occurred_on, note, reasons)


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def show_sample(project: dict, name: str) -> dict:
    sample = get_sample(project, name)
    return {**sample, "status": status(project, sample), "uses": uses_of(project, sample)}


def status(project: dict, sample: dict) -> dict:
    """A sample's own uses and, separately, uses of overlapping samples that also saw its data."""
    uses = uses_of(project, sample)
    direct = [u for u in uses if u["sample"] == sample["name"]]
    overlapping = [u for u in uses if u["sample"] != sample["name"]]
    return {"state": "used" if uses else "unused",
            "uses": len(direct), "overlapping_uses": len(overlapping),
            "by_purpose": dict(Counter(u["purpose"] for u in direct)),
            "overlapping_by_purpose": dict(Counter(u["purpose"] for u in overlapping)),
            "latest": max((u["occurred_on"] for u in uses), default=None)}


def purpose_counts(counts: dict) -> str:
    return ", ".join(f"{p} {n}" for p, n in sorted(counts.items())) or "none"


def ledger_lines(project: dict) -> list[str]:
    samples = list_samples(project)
    if not samples:
        return ["(no samples defined; use 'nullfield sample define')"]
    lines = []
    for sample in samples:
        window = f"{sample['start'] or '…'} → {sample['end'] or '…'}" if sample["start"] or sample["end"] else "undated"
        state = status(project, sample)
        if state["state"] == "unused":
            summary = "UNUSED"
        else:
            summary = f"own: {purpose_counts(state['by_purpose'])}"
            if state["overlapping_uses"]:
                summary += f"; via overlapping samples: {purpose_counts(state['overlapping_by_purpose'])}"
            summary += f"; latest {state['latest']}"
        lines.append(f"- {sample['name']} [{sample['role']}] {sample['dataset']} {window} — {summary}")
    return lines
