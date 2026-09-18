"""Patch a generated thunderdome eval script so it can actually run, then print its path.

Generated scripts hard-code /mnt/vast/envs/login/mistral_login_*/bin/python, which has no
thunderdome_tasks module and is 3.10 anyway (SyntaxError on PEP 695 generics). They also
inherit none of the env the job needs.

Usage: patch_eval.py SRC DST VENV_PYTHON
"""

import pathlib
import re
import sys

ENV = (
    "\n. /etc/shell-config/shell-config.sh >/dev/null 2>&1\n"
    "export LANGUAGE=en_US.UTF-8 LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8\n"
    "ulimit -n 1048576\n"
)

src, dst, py = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
text = re.sub(r"/mnt/vast/envs/login/mistral_login_[^/]*/bin/python", py, src.read_text())
lines = text.splitlines(True)
if not any("shell-config.sh" in ln for ln in lines):
    i = max(i for i, ln in enumerate(lines) if ln.startswith("#SBATCH")) + 1
    lines.insert(i, ENV)
dst.write_text("".join(lines))

leftover = dst.read_text().count("envs/login")
print(f"wrote {dst}")
print(f"login-python refs left (want 0): {leftover}")
sys.exit(1 if leftover else 0)
