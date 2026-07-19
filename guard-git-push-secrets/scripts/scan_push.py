#!/usr/bin/env python3
"""Scan Git objects that are about to be pushed for sensitive data."""

from __future__ import annotations

import argparse
import fnmatch
import math
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional


MAX_TEXT_BLOB_BYTES = 5 * 1024 * 1024
ALLOWLIST_NAME = ".git-sensitive-scan-allowlist"

SENSITIVE_BASENAMES = {
    ".git-credentials",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "credentials",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
}
SENSITIVE_SUFFIXES = (".jks", ".key", ".kdbx", ".keystore", ".p12", ".pfx")
SENSITIVE_PATHS = (
    ".aws/credentials",
    ".docker/config.json",
    ".kube/config",
    ".ssh/*",
)
SAFE_ENV_SUFFIXES = (".dist", ".example", ".sample", ".template")

CONTENT_RULES = (
    (
        "private key",
        re.compile(
            rb"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----|"
            rb"-----BEGIN OPENSSH PRIVATE KEY-----|-----BEGIN PGP PRIVATE KEY BLOCK-----"
        ),
    ),
    ("AWS access key", re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    (
        "GitHub token",
        re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{20,255})\b"),
    ),
    ("GitLab token", re.compile(rb"\bglpat-[A-Za-z0-9_-]{20,255}\b")),
    ("Slack token", re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,255}\b")),
    ("Stripe live key", re.compile(rb"\bsk_live_[A-Za-z0-9]{16,255}\b")),
    ("Google API key", re.compile(rb"\bAIza[0-9A-Za-z_-]{35}\b")),
    (
        "SendGrid API key",
        re.compile(rb"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b"),
    ),
    (
        "credential-bearing URL",
        re.compile(rb"\b[a-z][a-z0-9+.-]{1,20}://[^\s/:@]{1,128}:[^\s/@]{6,128}@", re.I),
    ),
)

GENERIC_ASSIGNMENT = re.compile(
    rb"(?im)^\s*[A-Za-z0-9_.-]*(?:api[_-]?key|client[_-]?secret|access[_-]?token|"
    rb"auth[_-]?token|password|passwd|private[_-]?key|secret)[A-Za-z0-9_.-]*\s*[:=]\s*"
    rb"[\"']?([^\s\"'#,;]{12,512})"
)
PLACEHOLDER_WORDS = {
    "changeme",
    "dummy",
    "example",
    "fake",
    "placeholder",
    "redacted",
    "replace_me",
    "sample",
    "test",
    "todo",
    "your_key_here",
    "your_token_here",
}


class GitError(RuntimeError):
    pass


def git(repo: Path, *args: str, input_data: Optional[bytes] = None) -> bytes:
    process = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode != 0:
        message = process.stderr.decode("utf-8", "replace").strip()
        raise GitError(message or f"git {' '.join(args)} failed")
    return process.stdout


def repository_root(repo: Path) -> Path:
    root = git(repo, "rev-parse", "--show-toplevel").decode().strip()
    return Path(root).resolve()


def load_allowlist(root: Path) -> list[str]:
    allowlist = root / ALLOWLIST_NAME
    if not allowlist.is_file():
        return []
    patterns = []
    for raw_line in allowlist.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            patterns.append(line.removeprefix("./"))
    return patterns


def is_allowlisted(path: str, patterns: Iterable[str]) -> bool:
    normalized = path.removeprefix("./")
    return any(fnmatch.fnmatchcase(normalized, pattern) for pattern in patterns)


def sensitive_path_rule(path: str) -> str | None:
    normalized = path.replace("\\", "/").lower().removeprefix("./")
    basename = normalized.rsplit("/", 1)[-1]
    if basename == ".env" or (
        basename.startswith(".env.") and not basename.endswith(SAFE_ENV_SUFFIXES)
    ):
        return "environment file"
    if basename in SENSITIVE_BASENAMES:
        return "credential filename"
    if basename.endswith(SENSITIVE_SUFFIXES):
        return "private key or credential store"
    if any(fnmatch.fnmatchcase(normalized, pattern) for pattern in SENSITIVE_PATHS):
        return "credential path"
    return None


def shannon_entropy(value: bytes) -> float:
    if not value:
        return 0.0
    counts = {byte: value.count(byte) for byte in set(value)}
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def generic_secret_detected(data: bytes) -> bool:
    for match in GENERIC_ASSIGNMENT.finditer(data):
        value = match.group(1).strip().lower()
        printable = value.decode("ascii", "ignore")
        if any(word in printable for word in PLACEHOLDER_WORDS):
            continue
        if value.startswith((b"${", b"{{", b"<")):
            continue
        if len(set(value)) >= 8 and shannon_entropy(value) >= 3.2:
            return True
    return False


def content_findings(data: bytes) -> list[str]:
    if b"\x00" in data[:8192]:
        return []
    findings = [name for name, pattern in CONTENT_RULES if pattern.search(data)]
    if generic_secret_detected(data):
        findings.append("high-entropy secret assignment")
    return findings


def is_zero_oid(value: str) -> bool:
    return bool(value) and set(value) == {"0"}


def commits_from_updates(repo: Path, updates: Iterable[str], remote_name: str) -> set[str]:
    commits: set[str] = set()
    for line in updates:
        fields = line.split()
        if len(fields) != 4:
            raise GitError("received malformed pre-push ref data")
        _local_ref, local_oid, _remote_ref, remote_oid = fields
        if is_zero_oid(local_oid):
            continue
        try:
            git(repo, "rev-parse", "--verify", f"{local_oid}^{{commit}}")
        except GitError:
            continue
        if is_zero_oid(remote_oid):
            args = ["rev-list", local_oid]
            if remote_name and remote_name not in {".", "(delete)"}:
                args.extend(["--not", f"--remotes={remote_name}"])
        else:
            args = ["rev-list", f"{remote_oid}..{local_oid}"]
        output = git(repo, *args).decode().splitlines()
        commits.update(output)
    return commits


def commits_from_ranges(repo: Path, ranges: Iterable[str]) -> set[str]:
    commits: set[str] = set()
    for revision_range in ranges:
        commits.update(git(repo, "rev-list", revision_range).decode().splitlines())
    return commits


def changed_paths(repo: Path, commit: str) -> list[str]:
    output = git(
        repo,
        "diff-tree",
        "--root",
        "-m",
        "--no-commit-id",
        "--name-only",
        "--diff-filter=AMCR",
        "-r",
        "-z",
        commit,
    )
    return [item.decode("utf-8", "surrogateescape") for item in output.split(b"\0") if item]


def blob_oid(repo: Path, commit: str, path: str) -> str | None:
    try:
        oid = git(repo, "rev-parse", f"{commit}:{path}").decode().strip()
        if git(repo, "cat-file", "-t", oid).strip() != b"blob":
            return None
        return oid
    except GitError:
        return None


def display_path(path: str) -> str:
    return path.encode("unicode_escape", "backslashreplace").decode("ascii", "replace")


def scan(repo: Path, commits: Iterable[str], allowlist: list[str]) -> tuple[list[tuple[str, str]], int]:
    findings: set[tuple[str, str]] = set()
    skipped_large = 0
    inspected_blobs: set[tuple[str, str]] = set()
    for commit in commits:
        for path in changed_paths(repo, commit):
            if is_allowlisted(path, allowlist):
                continue
            path_rule = sensitive_path_rule(path)
            if path_rule:
                findings.add((path, path_rule))
            oid = blob_oid(repo, commit, path)
            if oid is None or (oid, path) in inspected_blobs:
                continue
            inspected_blobs.add((oid, path))
            size = int(git(repo, "cat-file", "-s", oid).decode().strip())
            if size > MAX_TEXT_BLOB_BYTES:
                skipped_large += 1
                continue
            data = git(repo, "cat-file", "blob", oid)
            for rule in content_findings(data):
                findings.add((path, rule))
    return sorted(findings), skipped_large


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("remote_name", nargs="?", default="", help=argparse.SUPPRESS)
    parser.add_argument("remote_location", nargs="?", default="", help=argparse.SUPPRESS)
    parser.add_argument("--repo", default=os.getcwd(), help="Git repository to inspect")
    parser.add_argument("--range", dest="ranges", action="append", default=[], help="Git revision range")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        repo = repository_root(Path(args.repo))
        allowlist = load_allowlist(repo)
        if args.ranges:
            commits = commits_from_ranges(repo, args.ranges)
        else:
            commits = commits_from_updates(repo, sys.stdin.read().splitlines(), args.remote_name)
        findings, skipped_large = scan(repo, commits, allowlist)
    except (GitError, OSError, UnicodeError, ValueError) as error:
        print(f"[secret-scan] ERROR: {error}", file=sys.stderr)
        print("[secret-scan] Push blocked because the scan could not complete safely.", file=sys.stderr)
        return 2

    if findings:
        print("[secret-scan] Push blocked: sensitive data may be present.", file=sys.stderr)
        for path, rule in findings:
            print(f"  - {display_path(path)} ({rule})", file=sys.stderr)
        print(
            f"[secret-scan] Review the files. For verified fixtures, add narrow globs to {ALLOWLIST_NAME}.",
            file=sys.stderr,
        )
        return 1

    summary = f"[secret-scan] OK: scanned {len(commits)} outgoing commit(s)"
    if skipped_large:
        summary += f"; skipped content of {skipped_large} blob(s) over 5 MiB"
    print(summary + ".", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
