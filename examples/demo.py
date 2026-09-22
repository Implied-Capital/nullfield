"""Exercise the installed CLI against disposable data, without model calls."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    with tempfile.TemporaryDirectory(prefix="qr-demo-") as directory:
        root = Path(directory)

        def qr(*args, markdown=False):
            result = subprocess.run([sys.executable, "-m", "quant_research", "--home", str(root / "registry"), *args],
                                    check=True, text=True, capture_output=True)
            return result.stdout if markdown else json.loads(result.stdout)

        code = root / "shared-code"
        code.mkdir()
        script = code / "experiment.py"
        script.write_text("gross = 0.01\ncost = 0.02\nprint(f'net={gross-cost:.3f}')\n")
        for alias in ("options-rv", "independent-study"):
            qr("project", "create", alias, "--name", alias, "--objective", "Exercise research record keeping.")
            qr("resource", "add", "--project", alias, "code", str(code), "--kind", "directory")
        codex = qr("session", "start", "options-rv", "--agent", "codex")["id"]
        claude = qr("session", "start", "options-rv", "--agent", "claude")["id"]
        study = qr("study", "create", "--session", codex, "--title", "Synthetic cost example",
                   "--plan", "Check the arithmetic of a made-up gross return and cost. This is not market evidence.")
        run = qr("run", "start", "--session", codex, "--study", study["id"], "--cwd", str(code),
                 "--input", "experiment.py", "--", sys.executable, "experiment.py")
        qr("entry", "add", "--session", codex, "--study", study["id"], "--kind", "finding",
           "--title", "Synthetic costs exceed gross return", "--body", "Only arithmetic on made-up numbers; no financial inference.",
           "--evidence", "run:" + run["id"])
        assert qr("search", "--session", claude, "synthetic costs")
        assert not qr("search", "--project", "independent-study", "synthetic costs")
        print(qr("context", "--session", claude, markdown=True))
        print("Demo passed: Claude can continue Codex's study; the other project's notebook is separate.")


if __name__ == "__main__":
    main()
