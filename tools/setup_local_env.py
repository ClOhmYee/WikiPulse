"""Create a local Compose environment without shipping a shared password."""
from __future__ import annotations

import argparse
import pathlib
import re
import secrets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path(".env"))
    args = parser.parse_args()
    template = pathlib.Path(__file__).resolve().parents[1] / ".env.example"
    if args.output.exists():
        print("Existing environment file preserved; no values were changed.")
        return 0
    text = template.read_text(encoding="utf-8")
    text, count = re.subn(r"(?m)^POSTGRES_PASSWORD=.*$",
                         "POSTGRES_PASSWORD=" + secrets.token_urlsafe(32), text)
    if count != 1:
        raise SystemExit("Expected exactly one POSTGRES_PASSWORD template entry.")
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    try:
        args.output.chmod(0o600)
    except OSError:
        pass
    print("Created local environment with a random DB password. Keep it out of Git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
