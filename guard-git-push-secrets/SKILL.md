---
name: guard-git-push-secrets
description: Install and maintain a repository-local Git pre-push hook that scans the exact commits about to be pushed for sensitive filenames and secret-like content, then blocks the push when risks are found. Use when a user asks to protect git push, prevent secrets or credential files from reaching a remote, add an automatic pre-push security check, audit outgoing commits, update the hook, or remove this protection.
---

# Guard Git Push Secrets

Install a repository-local `pre-push` hook backed by the bundled scanner. Preserve an existing hook by chaining it after the security scan.

## Install or update

1. Resolve the target repository. Use the current repository unless the user names another one.
2. Run:

   ```bash
   python3 <skill-directory>/scripts/install.py --repo <repository>
   ```

3. Report the active hooks directory and whether an existing hook was preserved.
4. Do not run `git push` merely to test the installation unless the user requested a push. Use the isolated self-test instead:

   ```bash
   python3 <skill-directory>/scripts/self_test.py
   ```

The installer copies the scanner into the repository's active Git hooks directory, so the hook continues to work without loading this skill. Re-run the installer after changing the bundled scanner.

The hook runs before ordinary `git push` commands. Git's explicit `--no-verify` option bypasses all `pre-push` hooks; do not present this client-side check as a substitute for server-side secret scanning or credential rotation.

## Detection behavior

Scan every commit newly reachable by each ref in the current push, including intermediate commits that add and later remove a secret. Block on:

- Sensitive paths such as `.env`, private-key stores, Git credential files, SSH private keys, and common cloud credential locations.
- Private-key blocks, provider-specific access tokens, credential-bearing URLs, and high-confidence secret assignments.

Print only the rule name and file path; never print the detected secret. Skip content inspection for binary blobs and blobs over 5 MiB, while still applying filename checks.

## Allow intentional fixtures

Create `.git-sensitive-scan-allowlist` at the repository root only after reviewing the finding. Put one repository-relative glob per line; blank lines and lines beginning with `#` are ignored.

```text
# Known fake credentials used by tests
tests/fixtures/**
examples/demo.env
```

An allowlisted path bypasses both filename and content findings. Prefer a narrow file path over a broad directory. Commit the allowlist when the exception should apply to collaborators.

## Scan manually

Use a Git revision range without installing or pushing:

```bash
python3 <skill-directory>/scripts/scan_push.py --repo <repository> --range <remote-ref>..HEAD
```

Repeat `--range` to scan multiple ranges. Exit status `1` means findings were detected; status `2` means the scan could not complete safely.

## Remove

Run:

```bash
python3 <skill-directory>/scripts/install.py --repo <repository> --uninstall
```

Restore the preserved hook when present. Remove only files managed by this skill.
