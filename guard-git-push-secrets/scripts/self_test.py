#!/usr/bin/env python3
"""Run an isolated end-to-end test of the pre-push hook."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional


def run(
    *command: str,
    cwd: Optional[Path] = None,
    expected: int = 0,
) -> subprocess.CompletedProcess:
    process = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if process.returncode != expected:
        raise AssertionError(
            f"expected exit {expected}, got {process.returncode}: {' '.join(command)}\n"
            f"stdout:\n{process.stdout}\nstderr:\n{process.stderr}"
        )
    return process


def write(path: Path, content: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(0o755)


def commit(repo: Path, message: str, *paths: str) -> None:
    run("git", "add", "--", *paths, cwd=repo)
    run("git", "commit", "-m", message, cwd=repo)


def main() -> int:
    installer = Path(__file__).with_name("install.py").resolve()
    fake_token = "ghp_" + ("A" * 36)

    try:
        with tempfile.TemporaryDirectory(prefix="guard-git-push-secrets-test-") as temporary:
            root = Path(temporary)
            remote = root / "remote.git"
            repo = root / "repo"
            run("git", "init", "--bare", str(remote))
            run("git", "init", str(repo))
            run("git", "branch", "-M", "main", cwd=repo)
            run("git", "config", "user.name", "Secret Scan Test", cwd=repo)
            run("git", "config", "user.email", "secret-scan@example.invalid", cwd=repo)
            run("git", "remote", "add", "origin", str(remote), cwd=repo)

            original_hook = repo / ".git" / "hooks" / "pre-push"
            original_content = "#!/bin/sh\ntouch .original-hook-ran\n"
            write(original_hook, original_content, executable=True)

            write(repo / "README.md", "safe content\n")
            commit(repo, "initial", "README.md")
            result = run(sys.executable, str(installer), "--repo", str(repo))
            if "preserved and chained" not in result.stdout:
                raise AssertionError("installer did not report preserving the existing hook")
            run(sys.executable, str(installer), "--repo", str(repo))
            run("git", "push", "-u", "origin", "main", cwd=repo)
            if not (repo / ".original-hook-ran").exists():
                raise AssertionError("preserved pre-push hook was not invoked")

            write(repo / ".env", "DATABASE_PASSWORD=a-realistic-secret-value-123\n")
            commit(repo, "add environment", ".env")
            blocked = run("git", "push", "origin", "main", cwd=repo, expected=1)
            if ".env (environment file)" not in blocked.stderr:
                raise AssertionError("sensitive .env file was not reported")
            if "a-realistic-secret-value-123" in blocked.stderr:
                raise AssertionError("scanner leaked the detected secret")

            write(repo / ".git-sensitive-scan-allowlist", ".env\n")
            commit(repo, "allow reviewed fixture", ".git-sensitive-scan-allowlist")
            run("git", "push", "origin", "main", cwd=repo)

            write(repo / "config.txt", f"token={fake_token}\n")
            commit(repo, "temporarily add token", "config.txt")
            (repo / "config.txt").unlink()
            run("git", "add", "-u", "--", "config.txt", cwd=repo)
            run("git", "commit", "-m", "remove token", cwd=repo)
            blocked = run("git", "push", "origin", "main", cwd=repo, expected=1)
            if "config.txt (GitHub token)" not in blocked.stderr:
                raise AssertionError("secret in an intermediate commit was not reported")
            if fake_token in blocked.stderr:
                raise AssertionError("scanner leaked the provider token")

            with (repo / ".git-sensitive-scan-allowlist").open("a", encoding="utf-8") as stream:
                stream.write("config.txt\n")
            commit(repo, "allow reviewed token fixture", ".git-sensitive-scan-allowlist")
            run("git", "push", "origin", "main", cwd=repo)

            run(sys.executable, str(installer), "--repo", str(repo), "--uninstall")
            if original_hook.read_text(encoding="utf-8") != original_content:
                raise AssertionError("uninstall did not restore the original hook")

    except (AssertionError, OSError) as error:
        print(f"SELF-TEST FAILED: {error}", file=sys.stderr)
        return 1

    print("SELF-TEST PASSED: block, allowlist, history scan, hook chaining, and restore all work.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
