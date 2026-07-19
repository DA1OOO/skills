#!/usr/bin/env python3
"""Install, update, or remove the guard-git-push-secrets pre-push hook."""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


MARKER = "# guard-git-push-secrets managed hook"
SCANNER_NAME = "guard-git-push-secrets.py"
BACKUP_NAME = "pre-push.guard-git-push-secrets.original"
HOOK = f'''#!/bin/sh
{MARKER}

hook_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
input_file=$(mktemp "${{TMPDIR:-/tmp}}/guard-git-push-secrets.XXXXXX") || exit 2
trap 'rm -f "$input_file"' EXIT HUP INT TERM
cat > "$input_file" || exit 2

python3 "$hook_dir/{SCANNER_NAME}" "$@" < "$input_file"
scan_status=$?
if [ "$scan_status" -ne 0 ]; then
    exit "$scan_status"
fi

if [ -x "$hook_dir/{BACKUP_NAME}" ]; then
    "$hook_dir/{BACKUP_NAME}" "$@" < "$input_file"
    exit $?
fi

exit 0
'''


class InstallError(RuntimeError):
    pass


def git(repo: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        raise InstallError(process.stderr.strip() or f"git {' '.join(args)} failed")
    return process.stdout.strip()


def atomic_write(path: Path, content: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def resolve_hooks_dir(repo: Path) -> Path:
    try:
        raw = git(repo, "rev-parse", "--path-format=absolute", "--git-path", "hooks")
    except InstallError:
        raw = git(repo, "rev-parse", "--git-path", "hooks")
    path = Path(raw)
    if not path.is_absolute():
        path = repo / path
    return path.resolve()


def install(repo: Path) -> tuple[Path, bool]:
    git(repo, "rev-parse", "--git-dir")
    hooks_dir = resolve_hooks_dir(repo)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "pre-push"
    scanner_path = hooks_dir / SCANNER_NAME
    backup_path = hooks_dir / BACKUP_NAME
    source_scanner = Path(__file__).with_name("scan_push.py")
    if not source_scanner.is_file():
        raise InstallError(f"bundled scanner is missing: {source_scanner}")
    scanner_text = source_scanner.read_text(encoding="utf-8")
    preserved = False
    moved_original = False

    try:
        if hook_path.exists() or hook_path.is_symlink():
            try:
                managed = MARKER in hook_path.read_text(encoding="utf-8", errors="replace")
            except OSError as error:
                raise InstallError(f"cannot inspect existing hook: {error}") from error
            if not managed:
                if backup_path.exists() or backup_path.is_symlink():
                    raise InstallError(f"refusing to overwrite existing backup: {backup_path}")
                os.replace(hook_path, backup_path)
                moved_original = True
                preserved = True
            else:
                preserved = backup_path.exists() or backup_path.is_symlink()

        mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
        atomic_write(scanner_path, scanner_text, mode)
        atomic_write(hook_path, HOOK, mode)
    except Exception:
        if moved_original and not hook_path.exists() and backup_path.exists():
            os.replace(backup_path, hook_path)
        raise
    return hooks_dir, preserved


def uninstall(repo: Path) -> tuple[Path, bool]:
    git(repo, "rev-parse", "--git-dir")
    hooks_dir = resolve_hooks_dir(repo)
    hook_path = hooks_dir / "pre-push"
    scanner_path = hooks_dir / SCANNER_NAME
    backup_path = hooks_dir / BACKUP_NAME
    restored = False

    if hook_path.exists() or hook_path.is_symlink():
        managed = MARKER in hook_path.read_text(encoding="utf-8", errors="replace")
        if not managed:
            raise InstallError(f"refusing to remove unmanaged hook: {hook_path}")
        hook_path.unlink()
    if scanner_path.exists() or scanner_path.is_symlink():
        scanner_path.unlink()
    if backup_path.exists() or backup_path.is_symlink():
        os.replace(backup_path, hook_path)
        restored = True
    return hooks_dir, restored


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.getcwd(), help="Target Git repository")
    parser.add_argument("--uninstall", action="store_true", help="Remove the managed hook")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    try:
        if args.uninstall:
            hooks_dir, restored = uninstall(repo)
            detail = "restored the previous pre-push hook" if restored else "no previous hook was present"
            print(f"Removed guard-git-push-secrets from {hooks_dir}; {detail}.")
        else:
            hooks_dir, preserved = install(repo)
            detail = "preserved and chained the previous pre-push hook" if preserved else "installed a new pre-push hook"
            print(f"Installed guard-git-push-secrets in {hooks_dir}; {detail}.")
    except (InstallError, OSError, UnicodeError) as error:
        print(f"Installation failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
