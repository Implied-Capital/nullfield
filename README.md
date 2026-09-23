# Nullfield

Skills and persistent memory for quantitative research with coding agents.

A small Python research layer for **Codex and Claude Code**. It provides shared
research skills, independent projects, and a persistent notebook. Your existing
agent supplies the model, tools, editing, and execution loop.

Projects are research agendas, not repositories. One project can reference
several repositories, and multiple projects can share the same repository while
keeping separate research histories.

Python 3.11+, no runtime dependencies. MIT licensed.

## Install

Clone the repository and install using Python 3.11 or newer (for example, Python 3.12):

```bash
git clone https://github.com/Implied-Capital/nullfield.git
cd nullfield
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
nullfield --help
```

For a globally available command, `pipx install .` or `uv tool install .` also
works. Activate the virtual environment to use `nullfield` in a terminal. The skill
installer records the absolute Python command so agents can use the same
installation even when their PATH differs. Keep that environment in place, or
reinstall the skill with `--force` after moving the installation.

## Create a project

```bash
nullfield project create options-rv \
  --name 'Options relative value' \
  --objective 'Determine whether the signal survives realistic trading costs.'
```

By default the notebook is created at `~/.nullfield/projects/options-rv`.
Use `--path /absolute/notebook/location` to place it anywhere. That directory
must be new or empty. No repository initialization or code changes are required.

Attach local resources as needed:

```bash
nullfield resource add --project options-rv pricing /path/to/pricing --kind repo
nullfield resource add --project options-rv backtesting /path/to/backtesting --kind repo
nullfield resource add --project options-rv prices /path/to/prices.parquet --kind dataset
nullfield resource add --project options-rv paper https://example.org/paper --kind reference
```

Resources are named references. Adding one does not copy data, load it into an
agent, or change the host's workspace permissions. Reusing a resource name
updates its local binding. A `repo` resource should point to a Git checkout;
non-Git directories are usable but have no Git provenance snapshot.

## Use your existing agent

Install the same research skill into one or both agents:

```bash
nullfield skills install --agent both
# Or: --agent codex / --agent claude
```

This writes the shared skill with its local CLI command into `research/SKILL.md`
and its method references into `research/references/`,
under `~/.agents/skills` for Codex and
`~/.claude/skills` for Claude Code. `--target /path/to/skills` overrides the
destination for a single agent. It checks all bundled files for local changes
before writing and preserves them unless you explicitly pass `--force`.
Additional user-created files are left in place. No host configuration files are modified.

Then invoke it in your existing agent:

```text
Codex:       $research options-rv
Claude Code: /research options-rv
```

Ask it to continue a named study or investigate a question. The skill selects
the project, reads its brief and notebook index, searches relevant prior work,
and records experiments and conclusions. Only the matching skill body is loaded
by the host. The notebook context is an index; prior evidence is retrieved on demand.

The skill emphasizes measurement validity, competing explanations, simple
baselines, and exact agreement between tested and implemented behavior. It loads
deeper guidance when relevant:

- [Experiment design](src/nullfield/skills/research/references/experiment-design.md):
  meaningful comparisons, evaluation exposure, bounded search, and stopping decisions.
- [Measurement and validation](src/nullfield/skills/research/references/measurement-validation.md):
  input quality, economic accounting, executable prices, dependence, and portfolio feasibility.
- [Model-assisted measurement](src/nullfield/skills/research/references/model-measurement.md):
  historical information boundaries, evidence selection, and controls for model evaluations.
- [Research records](src/nullfield/skills/research/references/research-records.md):
  scoped findings, reproducible evidence, corrections, negative results, and handoffs.

These are research instructions followed by the host agent, not checks enforced
by the Python runner. Private hypotheses and strategy details belong in the
project notebook; the shared skill contains general methods.

Host integration references: [Codex skills](https://learn.chatgpt.com/docs/build-skills)
and [Claude Code skills](https://code.claude.com/docs/en/skills).

## Explicit session selection

```bash
nullfield session start options-rv --agent codex
```

The JSON result contains a research-session UUID. Pass that UUID with every
subsequent operation:

```bash
nullfield context --session SESSION_UUID
nullfield search --session SESSION_UUID 'transaction costs'
nullfield session show SESSION_UUID
```

A research session has an immutable project binding. Another session can use a
different project in the same working directory. There is no global active
project, cwd inference, or implicit selection of the latest session. Direct
scripts may use `--project ALIAS` instead of `--session UUID`.

These UUIDs are **nullfield session IDs**, not native Codex/Claude session IDs. They
persist across nullfield process restarts. The skill carries them in conversation and
handoff summaries; automatic host lifecycle hooks are not part of this MVP. If
the association is lost, select a project again or explicitly choose a recorded
session with `nullfield session list`. To switch projects, start a new research session.

## Studies, runs, and notebook entries

Create a bounded study with a Markdown plan. The example is a planning template,
not evidence that any strategy works:

```bash
nullfield study create --session SESSION_UUID \
  --title 'Does the signal survive costs?' --file examples/cost-study.md
```

Use the returned study UUID to record a command:

```bash
nullfield run start --session SESSION_UUID --study STUDY_UUID \
  --cwd /path/to/backtesting --timeout 300 \
  --input experiment.py --input prices.csv -- python experiment.py
```

The command receives normal arguments, not an implicit shell. All nullfield options
must precede `--`. Input paths are relative to `--cwd`. Each run records:

- The exact command, working directory, time budget, timestamps, and exit status.
- A copy and SHA-256 digest of the study plan before execution.
- SHA-256 digests of the explicitly declared input files.
- Git heads and tracked patches for the working directory and attached repo resources.
- Separate stdout and stderr files.

Failures, missing executables, interruptions, and timeouts produce run records
too. The CLI propagates the command's exit code (124 for timeout, 130 for an
interrupt, 127 for launch failure). On POSIX, timeout/interrupt cleanup targets
the command's process group. A successful process is marked `completed`; that
does not mean its scientific conclusion is validated.

Create a notebook entry after reviewing the evidence:

```bash
nullfield entry add --session SESSION_UUID --study STUDY_UUID \
  --kind finding --title 'The gain disappears under observed spreads' \
  --file finding.md --evidence run:RUN_UUID

nullfield entry add --session SESSION_UUID --study STUDY_UUID \
  --kind decision --title 'Stop this variant' \
  --body 'The tested fill assumption was too optimistic. Next: inspect execution data.'
```

Entry kinds: `observation`, `finding`, `decision`, `question`. Findings require
at least one evidence reference: `run:UUID`, `entry:UUID`, a file, or an HTTP(S)
URL. Run/entry IDs resolve within the selected project. External project evidence
can be referenced by file or URL, retaining its original scope in the prose.
URLs are stored without fetching. Existence checks do not establish scientific validity.

Read records with `nullfield study read`, `nullfield entry read`, or `nullfield run read`, followed by
`--session SESSION_UUID RECORD_UUID`. Each also supports `list`. Metadata commands
emit JSON; `context` emits Markdown. `--file -` reads Markdown from stdin. Search
matches all whitespace-separated query words, case-insensitively, across complete
entry bodies and study plans. It includes older and negative results.

## Evaluation-data ledger

Looking at outcomes cannot be undone. The ledger names evaluation samples and
records every use of them, across studies, sessions, and agents, so a later
study can see what its evaluation data have already been used for.

```bash
nullfield sample define --project options-rv fit-era --dataset labels \
  --start 2019-01-01 --end 2022-12-31 --role development
nullfield sample define --project options-rv holdout --dataset labels \
  --start 2023-01-01 --role holdout --description 'Reserved for frozen candidates'
```

A sample names a dataset and, optionally, a date range; omit `--start` or
`--end` for an open-ended range. Samples of the same dataset whose dates
intersect share history, so using a pooled 2019–2026 sample counts against a
2023 holdout. Undated samples (a fixed document set, for example) share history
only with themselves. Definitions are immutable: a changed boundary is a new sample.

Each use has a purpose: `fit` (estimate parameters), `select` (choose among
variants), `evaluate` (test a frozen candidate), or `inspect` (look at outcomes
for diagnosis or exploration). Record the uses of a run when starting it:

```bash
nullfield run start --session SESSION_UUID --study STUDY_UUID --cwd /path/to/backtesting \
  --sample fit-era:fit --sample holdout:evaluate -- python experiment.py
```

Or record work done outside the runner, including history, with `--date`:

```bash
nullfield sample use --session SESSION_UUID holdout --purpose select \
  --study STUDY_UUID --date 2026-08-06
```

The ledger refuses, and records nothing, when a use would compromise a sample:

- `evaluate` on a sample (or an overlapping one) that an earlier use already
  saw. A study repeating its own evaluation is allowed and remains visible.
- `fit`, `select`, or `inspect` on a holdout, or on a sample overlapping one.

`--acknowledge-conflicts` records the use anyway and stores the conflicts with
it; label the result as using previously seen data. Backfilled uses only
conflict with uses dated on or before them. `nullfield sample show NAME` lists
a sample's uses, and `context` summarizes every sample's status. Run uses are
recorded before launch, because a command that starts may read outcomes even
if it fails. The ledger records declared use; it cannot detect undeclared access.

## Storage and portability

```text
project.json                 Stable UUID, name, schema version
brief.md                     Research objective and editable project guidance
studies/<uuid>/
  record.json                Identity, title, creation time
  plan.md                    Experiment plan
entries/<uuid>/
  record.json                Kind, study association, evidence references
  note.md                    Human-readable observations and interpretation
runs/<uuid>/
  record.json                Command, provenance, status
  plan.md                    Protocol copied before execution
  code-*.patch               Tracked Git edits when applicable
  stdout.log / stderr.log    Experiment output
samples/<name>/
  record.json                Dataset, date range, role
uses/<uuid>/
  record.json                Sample, purpose, study/run, date, acknowledged conflicts
```

Notebook files are the source of research content and can be versioned in Git.
SQLite stores only local project aliases/paths, resource bindings, and research
sessions. The registry defaults to `~/.nullfield/registry.sqlite3`; override
with `NULLFIELD_HOME` or `nullfield --home PATH ...` (before the subcommand).

To move or clone a notebook:

```bash
nullfield project register options-rv /new/notebook/location
```

Registration preserves the manifest UUID. Re-registering that UUID updates its
local alias/path and existing sessions follow it. Each machine attaches its own
resource paths. Resource bindings and session IDs are machine-local; the notebook
travels independently. Absolute external evidence paths may need rebinding or
replacement with durable URLs when sharing across machines.

Records have unique directories and atomically replaced metadata files. SQLite
serializes registry writes. Separate local agents can append entries concurrently.
Record files remain editable by humans; the CLI does not rewrite old entries.
Use a new linked entry to supersede an earlier conclusion. Simultaneous direct
edits to the same Markdown file still need normal collaboration/version control.

## Develop and try an isolated example

```bash
python -m unittest discover -s tests -v
python examples/demo.py
```

The demo creates disposable projects, binds both agents, runs a synthetic command,
records a finding, and verifies isolation. It uses no model APIs, touches no real
research data, and does not install skills or change your registry.
