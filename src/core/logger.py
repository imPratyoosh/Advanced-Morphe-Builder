import os
import sys

IS_GITHUB: bool = bool(os.getenv("GITHUB_REPOSITORY"))


class BuildAbortError(Exception):
    pass

def _log(color: str, symbol: str, msg: str, gh_level: str | None = None) -> None:
    print(f"\033[0;{color}m[{symbol}] {msg}\033[0m", file=sys.stderr)
    if IS_GITHUB and gh_level:
        print(f"::{gh_level}::{msg}\n", file=sys.stderr)

def pr(msg: str) -> None:
    _log("32", "+", msg)

def epr(msg: str) -> None:
    _log("31", "-", msg, "error")

def wpr(msg: str) -> None:
    _log("33", "!", msg, "warning")

def abort(msg: str) -> None:
    epr(f"ABORT: {msg}")
    raise BuildAbortError(msg)