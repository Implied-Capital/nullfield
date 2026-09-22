---
name: research
description: >-
  Work on quant research projects with the qr CLI: select or resume a project,
  consult its shared research notebook, conduct experiments, and preserve evidence
  and next steps. Use when the user invokes research with a project alias or asks
  to continue a registered quant research study.
---

# Research

Use the installed `qr` CLI for project identity and research records. The host
(Codex or Claude Code) supplies reasoning, editing, execution tools, and session
management. Projects can span repositories or share a repository. The current
working directory never identifies the active research project.

## Select and orient

- If the user supplied a research-session UUID, run `qr session show UUID`,
  then `qr context --session UUID`.
- If the user supplied a project alias, run `qr session start ALIAS --agent codex`
  (use `--agent claude` in Claude Code). Save the returned research-session UUID
  in the conversation and any continuation summary; use `--session UUID` for
  subsequent work. A new agent conversation normally gets a new research session.
- With no selection, run `qr project list` and ask which project to use. If a
  session association was lost, don't infer it from the latest session or cwd.
- To create a project, use `qr project create ALIAS --name 'NAME' --objective
  'OBJECTIVE' --path /absolute/notebook/path`. The notebook directory must be new
  or empty. Register an existing notebook with `qr project register ALIAS PATH`.
- Read `qr context --session UUID`. Show the project name and current direction
  briefly, then search related work before proposing an investigation. Context
  is an index; open relevant plans, findings, decisions, and negative results.

If `QR_HOME` is configured, the CLI uses it. Otherwise its registry lives under
`~/.quant-research`. A user-supplied registry can be used consistently through
`qr --home PATH ...`. Resource access still follows the host's workspace rules;
registration alone does not grant filesystem access.

## Research process

Use the project's brief and the user's request to choose a bounded question.
For an empirical study, state the hypothesis, plausible mechanism, baseline,
data and feature timing, evaluation periods, costs, measurements, rejection
criteria, and experiment budget. Scale this detail to the question. Diagnostic
work and literature investigations may need a different plan.

Create a study with `qr study create --session UUID --title 'QUESTION' --file
/absolute/plan.md`. Plans are editable Markdown; each recorded run freezes a
copy of the plan as it existed before execution. A frozen copy records timing;
it does not prove an untouched holdout or prevent access to data.

Prefer experiments that distinguish explanations. Track inspected periods,
variants, and changes prompted by observed outcomes. A reused evaluation period
remains inspected across sessions and studies. Investigate coding, alignment,
and cost assumptions before treating a surprising metric as economic evidence.

Use the host's normal coding and analysis tools. When running an experiment,
record it through:

```bash
qr run start --session UUID --study STUDY_UUID --cwd /absolute/code/path \
  --timeout 300 --input experiment.py --input data.csv -- python experiment.py
```

Use an appropriate budget; inputs are resolved against `--cwd`. All qr options
precede `--`; the remaining arguments are executed directly, without a shell.
The result contains the run UUID and paths to stdout, stderr, metadata, and the
frozen plan. A nonzero CLI exit still leaves a run record. Read the output files
to assess the result. A completed process is not a validated research finding.
The runner records Git heads and tracked patches, but does not archive untracked
code, dependencies, or datasets. Add important files as `--input` to fingerprint
them; preserve source artifacts separately when reproduction requires it.

## Notebook operations

```bash
qr resource add --session UUID pricing /absolute/pricing --kind repo --description 'Pricing implementation'
qr search --session UUID 'transaction costs'
qr study list --session UUID
qr study read --session UUID STUDY_UUID
qr entry read --session UUID ENTRY_UUID
qr run read --session UUID RUN_UUID
qr entry add --session UUID --study STUDY_UUID --kind finding \
  --title 'Improvement disappears at observed spreads' --file /absolute/finding.md \
  --evidence run:RUN_UUID
```

Entry kinds are `observation`, `finding`, `decision`, and `question`. Findings
require evidence references: `run:UUID`, `entry:UUID`, an existing file, or a URL.
Evidence validation checks references, not whether they justify a claim.
Represent inconclusive and negative results explicitly. State each finding's
scope, assumptions, uncertainty, and contrary evidence in its Markdown body.

Record substantial revisions as new entries that cite earlier ones. Link to
another project's evidence by file or URL and preserve its original scope;
don't silently copy its conclusions into this project as established facts.
Finish a substantial investigation with a decision entry explaining what changed,
what remains uncertain, and the next action or reason to stop. Let the user's
objective and budget determine whether to continue autonomously.

## Sessions and continuation

Research-session IDs belong to qr, not to the host's native session system.
They persist in the registry, but this MVP does not install lifecycle hooks.
Carry the UUID in handoff summaries. If unavailable, ask for the project or
session, or use the explicit project in the user's request to start a new one.
Switching projects creates a new research session; other sessions are unaffected.
For direct scripted operations, `--project ALIAS` can replace `--session UUID`.
