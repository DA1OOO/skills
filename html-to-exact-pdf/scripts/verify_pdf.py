#!/usr/bin/env python3
"""Inspect a PDF and render a low-resolution PNG preview for visual QA."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path


def command(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    candidate = (
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override"
        / name
    )
    if candidate.is_file():
        return str(candidate)
    raise RuntimeError(f"Required command not found: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="PDF to inspect")
    parser.add_argument("--preview", required=True, type=Path, help="Output PNG path")
    parser.add_argument("--dpi", type=int, default=36, help="Preview DPI (default: 36)")
    args = parser.parse_args()

    pdf = args.input.expanduser().resolve()
    preview = args.preview.expanduser().resolve()
    if not pdf.is_file():
        raise FileNotFoundError(pdf)
    if pdf.suffix.lower() != ".pdf":
        raise ValueError(f"Input must be a PDF: {pdf}")
    if preview.suffix.lower() != ".png":
        raise ValueError(f"Preview must end in .png: {preview}")
    if args.dpi <= 0:
        raise ValueError("DPI must be positive")

    info = subprocess.run(
        [command("pdfinfo"), str(pdf)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    pages_match = re.search(r"^Pages:\s+(\d+)", info, re.MULTILINE)
    size_match = re.search(r"^Page size:\s+(.+)$", info, re.MULTILINE)
    pages = int(pages_match.group(1)) if pages_match else None
    if pages != 1:
        raise RuntimeError(f"Expected one continuous PDF page, found {pages}")

    preview.parent.mkdir(parents=True, exist_ok=True)
    prefix = preview.with_suffix("")
    subprocess.run(
        [
            command("pdftoppm"),
            "-f", "1",
            "-singlefile",
            "-png",
            "-r", str(args.dpi),
            str(pdf),
            str(prefix),
        ],
        check=True,
    )
    rendered = Path(f"{prefix}.png")
    if rendered != preview:
        rendered.replace(preview)

    print(json.dumps({
        "pdf": str(pdf),
        "pages": pages,
        "page_size": size_match.group(1).strip() if size_match else None,
        "bytes": pdf.stat().st_size,
        "preview": str(preview),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
