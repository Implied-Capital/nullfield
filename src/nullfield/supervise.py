"""Detached run supervisor.

`python -m nullfield.supervise --spawn RUN_DIRECTORY` starts the supervisor in a
new session and exits at once, so the supervisor is not a child of the caller.
`python -m nullfield.supervise RUN_DIRECTORY` executes the run and finalizes it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .experiments import execute


def main(argv: list[str]) -> int:
    if argv[:1] == ["--spawn"]:
        path = Path(argv[1])
        with (path / "supervisor.log").open("ab") as log:
            subprocess.Popen([sys.executable, "-m", "nullfield.supervise", str(path)],
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             start_new_session=os.name == "posix", close_fds=True)
        return 0
    execute(Path(argv[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
