from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from nullfield.experiments import run_experiment
from nullfield.integration import install_skill
from nullfield.ledger import define_sample, get_sample, list_samples, record_use, show_sample
from nullfield.store import (ResearchError, Store, add_entry, context,
                                 create_study, get_record, list_records, search)


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.home = self.root / "registry"
        self.store = Store(self.home)
        self.alpha = self.store.create_project("alpha", "Alpha research", self.root / "alpha", "Test a signal.")
        self.beta = self.store.create_project("beta", "Beta research", self.root / "beta", "Measure costs.")

    def tearDown(self):
        self.store.close()
        self.temporary.cleanup()

    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "nullfield", "--home", str(self.home), *args],
                              text=True, capture_output=True, timeout=20)

    def test_shared_repo_independent_sessions_and_memory(self):
        repo = self.root / "shared-repo"
        repo.mkdir()
        for project in (self.alpha, self.beta):
            self.store.add_resource(project, "code", str(repo), "repo", "Shared implementation")
        a = self.store.start_session(self.alpha, "codex")
        b = self.store.start_session(self.beta, "claude")
        add_entry(self.store.scope(None, a["id"]), "observation", "Alpha only", "A result", None, [])
        add_entry(self.store.scope(None, b["id"]), "observation", "Beta only", "B result", None, [])
        self.assertIn("Alpha only", context(self.store, self.alpha, a["id"]))
        self.assertNotIn("Beta only", context(self.store, self.alpha, a["id"]))
        self.assertEqual(search(self.beta, "Alpha only"), [])
        self.assertEqual(self.store.scope(None, a["id"])["id"], self.alpha["id"])

    def test_explicit_scope_required(self):
        with self.assertRaises(ResearchError):
            self.store.scope(None, None)
        with self.assertRaises(ResearchError):
            self.store.scope("alpha", self.store.start_session(self.beta, "manual")["id"])
        result = self.cli("entry", "list")
        self.assertEqual(result.returncode, 2)

    def test_session_survives_process_restart_and_project_move(self):
        session = self.store.start_session(self.alpha, "codex")
        moved = self.root / "moved-notebook"
        shutil.move(self.alpha["path"], moved)
        self.store.register_project("renamed", moved)
        other = Store(self.home)
        try:
            self.assertEqual(other.scope(None, session["id"])["path"], str(moved.resolve()))
            self.assertEqual(other.scope(None, session["id"])["alias"], "renamed")
        finally:
            other.close()

    def test_notebook_can_be_registered_on_a_different_machine(self):
        original = add_entry(self.alpha, "decision", "Stop this approach", "Costs dominate.", None, [])
        copy = self.root / "copied-notebook"
        shutil.copytree(self.alpha["path"], copy)
        other = Store(self.root / "another-registry")
        try:
            project = other.register_project("my-alias", copy)
            self.assertEqual(project["id"], self.alpha["id"])
            self.assertEqual(list_records(project, "entries")[0]["id"], original["id"])
            self.assertEqual(other.resources(project), [])
        finally:
            other.close()

    def test_duplicate_alias_does_not_create_or_overwrite_notebooks(self):
        unused = self.root / "unused"
        with self.assertRaises(ResearchError):
            self.store.create_project("alpha", "Replacement", unused, "Different objective")
        self.assertFalse(unused.exists())
        occupied = self.root / "occupied"
        occupied.mkdir()
        (occupied / "important.txt").write_text("keep me")
        with self.assertRaises(ResearchError):
            self.store.create_project("third", "Third", occupied, "Objective")
        self.assertEqual((occupied / "important.txt").read_text(), "keep me")

    def test_cross_project_links_are_rejected(self):
        study = create_study(self.alpha, "Alpha study", "Frozen plan")
        with self.assertRaises(ResearchError):
            add_entry(self.beta, "observation", "Wrong project", "Body", study["id"], [])
        entry = add_entry(self.alpha, "observation", "Alpha", "Body", None, [])
        with self.assertRaises(ResearchError):
            add_entry(self.beta, "finding", "Wrong evidence", "Body", None, [f"entry:{entry['id']}"])

    def test_finding_requires_resolvable_evidence(self):
        with self.assertRaises(ResearchError):
            add_entry(self.alpha, "finding", "Unsupported", "Body", None, [])
        with self.assertRaises(ResearchError):
            add_entry(self.alpha, "finding", "Missing file", "Body", None, [str(self.root / "missing")])
        source = add_entry(self.alpha, "observation", "Costs", "Transaction costs dominated the gain.", None, [])
        finding = add_entry(self.alpha, "finding", "Rejected", "Only under tested conditions.", None, [f"entry:{source['id']}"])
        self.assertEqual(finding["evidence"], [f"entry:{source['id']}"])
        self.assertEqual(search(self.alpha, "transaction COSTS")[0]["id"], source["id"])

    def test_search_includes_studies_and_old_negative_results(self):
        old = add_entry(self.alpha, "finding", "Rejected mean reversion", "Costs erase the effect.", None, ["https://example.org/evidence"])
        for i in range(12):
            add_entry(self.alpha, "observation", f"Unrelated {i}", "Fresh data", None, [])
        study = create_study(self.alpha, "Mean reversion retry", "Check different transaction costs.")
        matches = search(self.alpha, "mean reversion")
        self.assertEqual({r["id"] for r in matches}, {old["id"], study["id"]})
        self.assertNotIn(old["id"], context(self.store, self.alpha, None, limit=3))

    def test_concurrent_writers_do_not_lose_records(self):
        def write(i):
            local = Store(self.home)
            try:
                session = local.start_session(local.project("alpha"), "manual")
                return add_entry(local.scope(None, session["id"]), "observation", f"Parallel {i}", "Body", None, [])
            finally:
                local.close()
        with ThreadPoolExecutor(max_workers=6) as pool:
            records = list(pool.map(write, range(18)))
        self.assertEqual(len(list_records(self.alpha, "entries")), 18)
        self.assertEqual(len({r["id"] for r in records}), 18)
        self.assertEqual(len(self.store.list_sessions(self.alpha)), 18)

    def test_ids_cannot_escape_record_directory(self):
        with self.assertRaises(ResearchError):
            get_record(self.alpha, "entries", "../../beta/project")

    def test_alias_cannot_shadow_another_projects_id(self):
        with self.assertRaises(ResearchError):
            self.store.register_project(self.alpha["id"], self.beta["path"])
        self.assertEqual(self.store.project(self.alpha["id"])["alias"], "alpha")

    def test_replaced_manifest_does_not_redirect_existing_session(self):
        session = self.store.start_session(self.alpha, "manual")
        shutil.copyfile(Path(self.beta["path"]) / "project.json", Path(self.alpha["path"]) / "project.json")
        with self.assertRaises(ResearchError):
            self.store.scope(None, session["id"])

    def test_experiment_preserves_plan_output_and_input_hash(self):
        study = create_study(self.alpha, "Costs", "The original protocol.")
        data = self.root / "prices.csv"
        data.write_text("price\n100\n")
        result = run_experiment(self.alpha, study["id"], [sys.executable, "-c", "import sys; print('result=2'); print('diagnostic', file=sys.stderr)"], self.root, 10, ["prices.csv"], [])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(len(result["inputs"][0]["sha256"]), 64)
        (Path(study["path"]) / "plan.md").write_text("A changed protocol")
        self.assertEqual((Path(result["path"]) / "plan.md").read_text(), "The original protocol.\n")
        self.assertIn("result=2", (Path(result["path"]) / "stdout.log").read_text())
        self.assertIn("diagnostic", (Path(result["path"]) / "stderr.log").read_text())
        finding = add_entry(self.alpha, "finding", "Recorded", "Scope", study["id"], [f"run:{result['id']}"])
        self.assertEqual(finding["study_id"], study["id"])

    def test_failed_and_missing_commands_are_recorded(self):
        study = create_study(self.alpha, "Failure", "Expect an error")
        failed = run_experiment(self.alpha, study["id"], [sys.executable, "-c", "raise SystemExit(7)"], self.root, 10, [], [])
        missing = run_experiment(self.alpha, study["id"], [str(self.root / "does-not-exist")], self.root, 10, [], [])
        self.assertEqual((failed["status"], failed["returncode"]), ("failed", 7))
        self.assertEqual((missing["status"], missing["returncode"]), ("failed", 127))
        self.assertEqual(len(list_records(self.alpha, "runs")), 2)

    def test_timeout_is_terminal_and_does_not_leave_evidence_running(self):
        study = create_study(self.alpha, "Timeout", "Time budget one second")
        result = run_experiment(self.alpha, study["id"], [sys.executable, "-c", "import time; time.sleep(30)"], self.root, 1, [], [])
        saved = get_record(self.alpha, "runs", result["id"])
        self.assertEqual((saved["status"], saved["returncode"]), ("timed_out", 124))
        self.assertIsNotNone(saved["finished_at"])

    def test_cli_failed_run_propagates_exit_code_and_json(self):
        study = create_study(self.alpha, "Failure", "Exit nonzero")
        result = self.cli("run", "start", "--project", "alpha", "--study", study["id"], "--cwd", str(self.root),
                          "--", sys.executable, "-c", "raise SystemExit(6)")
        self.assertEqual(result.returncode, 6, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "failed")

    @unittest.skipUnless(os.name == "posix", "Process groups require POSIX")
    def test_timeout_kills_child_even_when_leader_exits(self):
        study = create_study(self.alpha, "Child cleanup", "Enforce the time budget")
        marker = self.root / "escaped-child"
        pidfile = self.root / "child.pid"
        child = ("import os, signal, time; from pathlib import Path; "
                 "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                 f"Path({str(pidfile)!r}).write_text(str(os.getpid())); "
                 f"time.sleep(2); Path({str(marker)!r}).write_text('escaped')")
        parent = f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(30)"
        try:
            result = run_experiment(self.alpha, study["id"], [sys.executable, "-c", parent], self.root, 1, [], [])
            self.assertEqual(result["status"], "timed_out")
            self.assertTrue(pidfile.exists(), "Child did not start")
            time.sleep(1.5)
            self.assertFalse(marker.exists(), "Child outlived the timed-out experiment")
        finally:
            if pidfile.exists():
                try:
                    os.kill(int(pidfile.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    @unittest.skipUnless(shutil.which("git"), "Git is not installed")
    def test_multi_repo_provenance_captures_tracked_changes(self):
        resources = []
        for name in ("one", "two"):
            repo = self.root / name
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "model.py").write_text("baseline = 1\n")
            subprocess.run(["git", "-C", str(repo), "add", "model.py"], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.org", "-c", "commit.gpgsign=false", "commit", "-qm", "baseline"], check=True)
            (repo / "model.py").write_text(f"baseline = {2 if name == 'one' else 3}\n")
            # A legitimate resource named 'cwd' must not overwrite the cwd patch.
            resources.append({"name": "cwd" if name == "two" else name, "kind": "repo", "location": str(repo)})
        study = create_study(self.alpha, "Multiple repos", "Compare implementations")
        result = run_experiment(self.alpha, study["id"], [sys.executable, "-c", "pass"], self.root / "one", 10, [], resources)
        self.assertEqual(len(result["code"]), 2)
        self.assertEqual(len({code["tracked_patch"] for code in result["code"]}), 2)
        for code in result["code"]:
            self.assertEqual(len(code["commit"]), 40)
            expected = 2 if Path(code["root"]).name == "one" else 3
            self.assertIn(f"+baseline = {expected}", (Path(result["path"]) / code["tracked_patch"]).read_text())

    def define_eras(self):
        define_sample(self.alpha, "fit-era", "labels", "2019-01-01", "2022-12-31", "development", "")
        define_sample(self.alpha, "holdout", "labels", "2023-01-01", "2026-05-21", "holdout", "")
        define_sample(self.alpha, "fresh", "labels", "2026-05-22", None, "holdout", "Open-ended")

    def test_samples_are_immutable_and_validated(self):
        self.define_eras()
        with self.assertRaises(ResearchError):
            define_sample(self.alpha, "holdout", "labels", "2020-01-01", None, "holdout", "Redefinition")
        with self.assertRaises(ResearchError):
            define_sample(self.alpha, "backwards", "labels", "2024-01-01", "2023-01-01", "development", "")
        with self.assertRaises(ResearchError):
            define_sample(self.alpha, "bad-date", "labels", "2024-13-01", None, "development", "")
        with self.assertRaises(ResearchError):
            get_sample(self.beta, "holdout")
        self.assertEqual([s["name"] for s in list_samples(self.alpha)], ["fit-era", "holdout", "fresh"])

    def test_evaluating_a_used_sample_is_refused_without_acknowledgement(self):
        self.define_eras()
        selection = create_study(self.alpha, "Pick a profile", "Compare profiles on the holdout.")
        confirm = create_study(self.alpha, "Confirm the profile", "Evaluate the chosen profile.")
        first = record_use(self.alpha, "holdout", "evaluate", selection["id"], "2026-08-06", "", False)
        self.assertEqual(first["acknowledged_conflicts"], [])
        # The same study repeating its own evaluation is not prior use by someone else.
        record_use(self.alpha, "holdout", "evaluate", selection["id"], "2026-08-07", "", False)
        with self.assertRaisesRegex(ResearchError, first["id"]):
            record_use(self.alpha, "holdout", "evaluate", confirm["id"], None, "", False)
        self.assertEqual(len(list_records(self.alpha, "uses")), 2, "A refused use must not be written")
        reused = record_use(self.alpha, "holdout", "evaluate", confirm["id"], None, "", True)
        self.assertEqual(len(reused["acknowledged_conflicts"]), 2)
        self.assertIn("used: evaluate 3", context(self.store, self.alpha, None))

    def test_fitting_or_inspecting_a_holdout_spends_it(self):
        self.define_eras()
        study = create_study(self.alpha, "Explore", "Look at everything.")
        with self.assertRaisesRegex(ResearchError, "holdout sample holdout"):
            record_use(self.alpha, "holdout", "inspect", study["id"], None, "", False)
        # A pooled development sample that overlaps a holdout spends it too.
        define_sample(self.alpha, "pooled", "labels", "2019-01-01", "2026-12-31", "development", "")
        with self.assertRaisesRegex(ResearchError, "holdout sample fresh, which overlaps pooled"):
            record_use(self.alpha, "pooled", "fit", study["id"], None, "", False)
        record_use(self.alpha, "fit-era", "fit", study["id"], None, "", False)

    def test_overlapping_samples_share_history_within_a_dataset(self):
        self.define_eras()
        define_sample(self.alpha, "l4-holdout", "labels", "2023-01-01", "2024-12-31", "holdout", "")
        define_sample(self.alpha, "other-data", "documents", "2023-01-01", "2024-12-31", "holdout", "")
        define_sample(self.alpha, "doc-set", "documents", None, None, "holdout", "Undated")
        study = create_study(self.alpha, "L4", "Evaluate 2023-24.")
        record_use(self.alpha, "l4-holdout", "evaluate", study["id"], "2026-07-04", "", False)
        later = create_study(self.alpha, "Optimizer", "Evaluate 2023-26.")
        with self.assertRaisesRegex(ResearchError, "via overlapping sample l4-holdout"):
            record_use(self.alpha, "holdout", "evaluate", later["id"], None, "", False)
        self.assertEqual(show_sample(self.alpha, "holdout")["status"]["overlapping_uses"], 1)
        self.assertEqual(show_sample(self.alpha, "fresh")["status"]["state"], "unused")
        self.assertEqual(show_sample(self.alpha, "other-data")["status"]["state"], "unused")
        record_use(self.alpha, "other-data", "evaluate", later["id"], None, "", False)
        self.assertEqual(show_sample(self.alpha, "doc-set")["status"]["state"], "unused")

    def test_backfilled_history_only_conflicts_with_earlier_uses(self):
        self.define_eras()
        late = create_study(self.alpha, "Late", "Later work")
        early = create_study(self.alpha, "Early", "Earlier work")
        record_use(self.alpha, "holdout", "evaluate", late["id"], "2026-09-06", "", False)
        record_use(self.alpha, "holdout", "evaluate", early["id"], "2026-07-04", "", False)
        with self.assertRaises(ResearchError):
            record_use(self.alpha, "holdout", "evaluate", early["id"], "2099-01-01", "", False)
        with self.assertRaisesRegex(ResearchError, "needs a --note"):
            record_use(self.alpha, "fit-era", "fit", None, None, "", False)
        self.assertIsNone(record_use(self.alpha, "fit-era", "fit", None, None, "Legacy calibration", False)["study_id"])

    def test_run_records_sample_use_and_refusal_leaves_no_run(self):
        self.define_eras()
        study = create_study(self.alpha, "Holdout run", "Evaluate the frozen candidate.")
        result = run_experiment(self.alpha, study["id"], [sys.executable, "-c", "pass"], self.root, 10, [], [],
                                [("holdout", "evaluate"), ("fit-era", "fit")])
        uses = [get_record(self.alpha, "uses", use_id) for use_id in result["sample_uses"]]
        self.assertEqual({(u["sample"], u["purpose"], u["run_id"]) for u in uses},
                         {("holdout", "evaluate", result["id"]), ("fit-era", "fit", result["id"])})
        other = create_study(self.alpha, "Second look", "Evaluate again.")
        with self.assertRaises(ResearchError):
            run_experiment(self.alpha, other["id"], [sys.executable, "-c", "pass"], self.root, 10, [], [],
                           [("fresh", "evaluate"), ("holdout", "evaluate")])
        self.assertEqual(len(list_records(self.alpha, "runs")), 1)
        self.assertEqual(len(list_records(self.alpha, "uses")), 2, "No partial uses from a refused run")

    def test_cli_sample_commands(self):
        defined = self.cli("sample", "define", "--project", "alpha", "holdout", "--dataset", "labels",
                           "--start", "2023-01-01", "--role", "holdout")
        self.assertEqual(defined.returncode, 0, defined.stderr)
        study = create_study(self.alpha, "Check", "Plan")
        used = self.cli("sample", "use", "--project", "alpha", "holdout", "--purpose", "evaluate", "--study", study["id"])
        self.assertEqual(used.returncode, 0, used.stderr)
        again = self.cli("run", "start", "--project", "alpha", "--study", create_study(self.alpha, "Other", "Plan")["id"],
                         "--cwd", str(self.root), "--sample", "holdout:evaluate", "--", sys.executable, "-c", "pass")
        self.assertEqual(again.returncode, 1)
        self.assertIn("--acknowledge-conflicts", again.stderr)
        bad = self.cli("run", "start", "--project", "alpha", "--study", study["id"], "--cwd", str(self.root),
                       "--sample", "holdout:peek", "--", sys.executable, "-c", "pass")
        self.assertEqual(bad.returncode, 2)
        shown = json.loads(self.cli("sample", "show", "--project", "alpha", "holdout").stdout)
        self.assertEqual(shown["status"]["by_purpose"], {"evaluate": 1})

    def test_skill_installation_is_portable_and_preserves_existing_edits(self):
        target = self.root / "skills"
        installed = install_skill("codex", target)
        self.assertEqual(install_skill("claude", target), installed)
        skill = Path(installed[0])
        skill.write_text("User's custom research skill")
        with self.assertRaises(ResearchError):
            install_skill("codex", target)
        self.assertEqual(skill.read_text(), "User's custom research skill")
        install_skill("codex", target, force=True)
        self.assertNotEqual(skill.read_text(), "User's custom research skill")

    def test_installed_skill_references_are_present_and_edits_are_preserved(self):
        target = self.root / "skills"
        installed = install_skill("codex", target)
        skill = Path(installed[0])
        references = re.findall(r"\]\((references/[^)]+)\)", skill.read_text())
        self.assertTrue(references)
        for relative in references:
            reference = skill.parent / relative
            self.assertIn(str(reference), installed)
            self.assertTrue(reference.read_text().strip())
        reference = skill.parent / references[0]
        original = reference.read_text()
        reference.write_text("My local research methods")
        skill.unlink()
        custom = skill.parent / "personal-notes.md"
        custom.write_text("Keep this user's file")
        with self.assertRaises(ResearchError):
            install_skill("claude", target)
        self.assertFalse(skill.exists(), "Conflict check must precede entrypoint creation")
        self.assertEqual(reference.read_text(), "My local research methods")
        install_skill("claude", target, force=True)
        self.assertEqual(reference.read_text(), original)
        self.assertEqual(custom.read_text(), "Keep this user's file")
        self.assertTrue(skill.is_file())

    def test_both_hosts_are_checked_before_installing_either_bundle(self):
        home = self.root / "user-home"
        claude_target = home / ".claude/skills"
        installed = install_skill("claude", claude_target)
        reference = next(Path(path) for path in installed if Path(path).parent.name == "references")
        reference.write_text("Local changes")
        with patch("nullfield.integration.Path.home", return_value=home):
            with self.assertRaises(ResearchError):
                install_skill("both")
            self.assertFalse((home / ".agents").exists())
            self.assertEqual(reference.read_text(), "Local changes")
            paths = install_skill("both", force=True)
        self.assertTrue(all(Path(path).is_file() for path in paths))
        self.assertEqual(len(paths), 2 * len(installed))
        self.assertEqual((home / ".agents/skills/research/references" / reference.name).read_text(), reference.read_text())


if __name__ == "__main__":
    unittest.main()
