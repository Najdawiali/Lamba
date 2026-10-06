#!/usr/bin/env python3
"""
Regenerate mobile/constants/legal.ts from backend/app/legal_content.py.

legal_content.py is the single source of truth for the privacy policy and the terms: the API serves
it as web pages (/privacy, /terms) and the mobile app embeds the same text as legal.ts, so the two
never disagree. Run this after every edit of legal_content.py:

    uv run scripts/generate-legal-ts.py            write mobile/constants/legal.ts
    uv run scripts/generate-legal-ts.py --check    write nothing; exit 1 if legal.ts is out of date

Standard library only, so `python scripts/generate-legal-ts.py` works too.
"""

import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # do not leave a __pycache__ next to legal_content.py

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "backend" / "app" / "legal_content.py"
TARGET = ROOT / "mobile" / "constants" / "legal.ts"

HEADER = """/**
 * Privacy Policy & Terms of Service — bilingual.
 *
 * GENERATED from backend/app/legal_content.py (the single source of truth, also served at
 * https://api.lambajo.com/privacy and /terms). Do not edit here: edit the backend file and regenerate,
 * so the app and the web pages never disagree.
 */

"""


def load_legal_content():
    spec = importlib.util.spec_from_file_location("legal_content", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ts_template(text: str) -> str:
    """Escape text for a JavaScript template literal."""
    return text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


def render() -> bytes:
    legal = load_legal_content()
    blocks = [
        "export const %s = `%s`;\n" % (name, ts_template(legal.to_plain_text(doc)))
        for name, doc in legal.DOCS.items()
    ]
    return (HEADER + "\n".join(blocks)).encode("utf-8")  # LF line endings, no BOM


def main(argv: list[str]) -> int:
    if any(arg != "--check" for arg in argv):
        print("usage: generate-legal-ts.py [--check]")
        return 2
    new = render()  # LF
    old = TARGET.read_bytes() if TARGET.exists() else b""
    # git on Windows (core.autocrlf) checks files out with CRLF: compare without line endings, and keep
    # the file's existing style when writing.
    crlf = b"\r\n" in old
    up_to_date = old.replace(b"\r\n", b"\n") == new
    if "--check" in argv:
        if up_to_date:
            print("legal.ts is up to date")
            return 0
        print("legal.ts is OUT OF DATE: run  uv run scripts/generate-legal-ts.py")
        return 1
    if up_to_date:
        print("legal.ts is already up to date (%d bytes)" % len(old))
        return 0
    data = new.replace(b"\n", b"\r\n") if crlf else new
    TARGET.write_bytes(data)
    print("wrote %s (%d bytes)" % (TARGET.relative_to(ROOT), len(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
