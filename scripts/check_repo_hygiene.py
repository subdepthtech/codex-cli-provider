#!/usr/bin/env python3
import re
import subprocess
import sys
from pathlib import Path


FORBIDDEN_STAGEABLE_PATHS = (
    ".env",
    "data/",
    ".venv/",
    "venv/",
    ".codex/",
    "codex-home/",
)

FORBIDDEN_FILENAMES = {
    "auth.json",
    "history.jsonl",
}

SECRET_PATTERNS = {
    "openai_api_key": re.compile(r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9_-]{20,}"),
    "github_token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}"),
    "github_fine_grained_token": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |PGP )?PRIVATE KEY-----"),
    "long_bearer_literal": re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{32,}"),
}


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def git_stageable_files() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        fail("could not list git-stageable files")
    return [line for line in completed.stdout.splitlines() if line]


def check_paths(paths: list[str]) -> None:
    for path in paths:
        normalized = path.replace("\\", "/")
        if normalized in FORBIDDEN_STAGEABLE_PATHS:
            fail(f"forbidden path is stageable: {path}")
        if any(normalized.startswith(prefix) for prefix in FORBIDDEN_STAGEABLE_PATHS if prefix.endswith("/")):
            fail(f"forbidden path is stageable: {path}")
        if Path(normalized).name in FORBIDDEN_FILENAMES:
            fail(f"forbidden credential/state filename is stageable: {path}")


def check_secret_patterns(paths: list[str]) -> None:
    for path in paths:
        file_path = Path(path)
        if not file_path.is_file():
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                fail(f"possible secret pattern '{name}' in {path}")


def main() -> None:
    paths = git_stageable_files()
    check_paths(paths)
    check_secret_patterns(paths)
    print("repo hygiene checks passed")


if __name__ == "__main__":
    main()
