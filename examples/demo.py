"""Exercise the installed CLI against disposable data, without model calls."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    with tempfile.TemporaryDirectory(prefix="nullfield-demo-") as directory:
        root = Path(directory)

        def nullfield(*args, markdown=False):
            result = subprocess.run([sys.executable, "-m", "nullfield", "--home", str(root / "registry"), *args],
                                    check=True, text=True, capture_output=True)
            return result.stdout if markdown else json.loads(result.stdout)

        code = root / "shared-code"
        code.mkdir()
        script = code / "experiment.py"
        script.write_text("gross = 0.01\ncost = 0.02\nprint(f'net={gross-cost:.3f}')\n")
        for alias in ("options-rv", "independent-study"):
            nullfield("project", "create", alias, "--name", alias, "--objective", "Exercise research record keeping.")
            nullfield("resource", "add", "--project", alias, "code", str(code), "--kind", "directory")
        codex = nullfield("session", "start", "options-rv", "--agent", "codex")["id"]
        claude = nullfield("session", "start", "options-rv", "--agent", "claude")["id"]
        study = nullfield("study", "create", "--session", codex, "--title", "Synthetic cost example",
                   "--plan", "Check the arithmetic of a made-up gross return and cost. This is not market evidence.")
        run = nullfield("run", "start", "--session", codex, "--study", study["id"], "--cwd", str(code),
                 "--input", "experiment.py", "--", sys.executable, "experiment.py")
        nullfield("entry", "add", "--session", codex, "--study", study["id"], "--kind", "finding",
           "--title", "Synthetic costs exceed gross return", "--body", "Only arithmetic on made-up numbers; no financial inference.",
           "--evidence", "run:" + run["id"])
        assert nullfield("search", "--session", claude, "synthetic costs")
        assert not nullfield("search", "--project", "independent-study", "synthetic costs")
        print(nullfield("context", "--session", claude, markdown=True))
        print("Demo passed: Claude can continue Codex's study; the other project's notebook is separate.")


if __name__ == "__main__":
    main()
