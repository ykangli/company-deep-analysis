# -*- coding: utf-8 -*-
"""Dependency resolution shared by the skill's scripts.

This module is deliberately side-effect free and imports only the standard
library, because `bootstrap.py` must be able to import it with a bare system
Python (before any virtual environment exists). The re-exec trampoline that
switches a running script into the venv lives in `_common.py`, not here.

Layout it assumes:

    <skill>/requirements.txt
    <skill>/scripts/_deps.py          <- this file
    <skill>/scripts/bootstrap.py
    <skill>/scripts/_common.py
"""
from __future__ import annotations

import os
import subprocess
import sys

# import-name -> pip package name
REQUIRED = [
    ("pandas", "pandas"),
    ("requests", "requests"),
    ("akshare", "akshare"),
    ("bs4", "beautifulsoup4"),
    ("lxml", "lxml"),
]

# Set to "1" once a process is running inside the managed venv, so the
# trampoline can never loop.
IN_VENV_ENV = "CDA_IN_VENV"

# Override the venv location entirely.
VENV_ENV = "CDA_VENV"

# Written inside the venv once dependencies verified importable.
MARKER = ".cda-deps-ok"


def scripts_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def skill_root() -> str:
    return os.path.dirname(scripts_dir())


def requirements_file() -> str:
    return os.path.join(skill_root(), "requirements.txt")


def user_data_dir() -> str:
    """Stable per-user location that survives skill reinstall/upgrade."""
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    return os.path.join(base, "company-deep-analysis")


def candidate_venvs():
    """Venv locations in priority order."""
    out = []
    env = os.environ.get(VENV_ENV)
    if env:
        out.append(os.path.abspath(env))
    out.append(os.path.join(user_data_dir(), ".venv"))
    out.append(os.path.join(skill_root(), ".venv"))
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def default_venv() -> str:
    return candidate_venvs()[0]


def venv_python(venv: str) -> str:
    if sys.platform == "win32":
        return os.path.join(venv, "Scripts", "python.exe")
    return os.path.join(venv, "bin", "python")


def is_ready(venv: str) -> bool:
    """A venv counts as usable only once bootstrap verified it."""
    return os.path.exists(venv_python(venv)) and os.path.exists(os.path.join(venv, MARKER))


def active_venv():
    """The first ready venv, or None."""
    for v in candidate_venvs():
        if is_ready(v):
            return v
    return None


def running_in(venv: str) -> bool:
    try:
        a = os.path.normcase(os.path.realpath(sys.executable))
        b = os.path.normcase(os.path.realpath(venv_python(venv)))
        return a == b
    except Exception:
        return False


def missing_packages():
    """Return the pip names of required packages that cannot be imported."""
    import importlib
    missing = []
    for mod, pkg in REQUIRED:
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(pkg)
    return missing


def has_everything() -> bool:
    return not missing_packages()


def _reexec_argv(python_exe: str):
    """Build the command line to relaunch this process inside the venv.

    `sys.argv` is NOT enough: for `python -c "code"` CPython sets argv to
    ['-c'] and keeps the code out of argv, and for `python -m mod` argv[0] is
    the module file. Exec'ing `[py] + sys.argv` would therefore drop the actual
    program. `sys.orig_argv` (3.10+) holds the real, complete command line.
    """
    orig = getattr(sys, "orig_argv", None)
    if orig and len(orig) > 1:
        return [python_exe] + list(orig[1:])
    # Python 3.9 fallback: only safe when a real script path was given.
    if sys.argv and sys.argv[0] and not sys.argv[0].startswith("-"):
        return [python_exe] + list(sys.argv)
    return None


def reexec_into_venv() -> None:
    """Switch this process into the managed venv, if one exists.

    Called at import time by `_common.py`. Safe to call when no venv exists,
    when already inside it, or when the interpreter refuses to exec.
    """
    if os.environ.get(IN_VENV_ENV) == "1":
        return
    venv = active_venv()
    if not venv:
        return
    if running_in(venv):
        os.environ[IN_VENV_ENV] = "1"
        return
    py = venv_python(venv)
    argv = _reexec_argv(py)
    if not argv:
        # Cannot reconstruct the command line (e.g. `python -c` on 3.9). Leave
        # the process alone rather than launching something incomplete.
        return
    os.environ[IN_VENV_ENV] = "1"
    try:
        # NOT os.execv: on Windows execv joins argv with spaces and does not
        # quote, so any argument containing a space (e.g. the code string after
        # `python -c`) arrives mangled. subprocess quotes correctly on every
        # platform, and inherits stdio so the caller sees normal output.
        raise SystemExit(subprocess.call(argv))
    except SystemExit:
        raise
    except Exception:
        # Could not re-exec (exotic interpreter, restricted env). Continue with
        # the current interpreter and let the import check report the problem.
        os.environ.pop(IN_VENV_ENV, None)
