"""Check tracked files and optionally every reachable Git object for sensitive data.
Output contains only file locations and rule names, never detected values.
"""
from __future__ import annotations
import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
RULES = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
    "api-token": re.compile(r"\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}|glpat-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AIza[0-9A-Za-z_-]{35}|(?:AKIA|ASIA)[A-Z0-9]{16}|ATATT[A-Za-z0-9_=-]{30,})"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\b"),
    "private-session-link": re.compile(r"https?://(?:claude\.ai/(?:code|chat)/|chatgpt\.com/(?:c|share)/)", re.I),
    "personal-phone": re.compile(r"(?<!\d)01[016789][- .]\d{3,4}[- .]\d{4}(?!\d)"),
}
BLOCKED_FILES = {".mcp.json", "CLAUDE.md", ".gitlab-ci.yml"}
BLOCKED_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".dump", ".db", ".sqlite", ".sqlite3"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "build", "dist", ".gradle", ".pytest_cache"}
EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
ALLOWED_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "contributors.invalid", "users.noreply.github.com"}

SECRET_ASSIGNMENT = re.compile(r"""(?im)^\s*["']?([A-Z_]*(?:API_KEY|LLM_GATEWAY_KEY|SECRET|PASSWORD|TOKEN))["']?\s*[:=]\s*(?:"([^"\r\n]*)"|'([^'\r\n]*)'|([^\s,#;\r\n]+))""")

def inspect(data: bytes, path: str) -> list[tuple[str, int, str]]:
    findings = []
    pure = pathlib.PurePosixPath(path)
    if path in BLOCKED_FILES or pure.suffix.lower() in BLOCKED_SUFFIXES or any(x in {".claude", ".agents", ".impeccable"} for x in pure.parts):
        findings.append((path, 1, "excluded-file"))
    if pure.name.startswith(".env") and pure.name != ".env.example":
        findings.append((path, 1, "environment-file"))
    if b"\0" in data[:8192]:
        return findings
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return findings
    for i, line in enumerate(text.splitlines(), 1):
        for label, pattern in RULES.items():
            if pattern.search(line):
                findings.append((path, i, label))
        for email in EMAIL.findall(line):
            domain = email.rsplit("@", 1)[1].lower()
            if domain not in ALLOWED_EMAIL_DOMAINS and not domain.endswith((".example.com", ".example.org", ".example.net")) and email.lower() != "noreply@anthropic.com":
                findings.append((path, i, "personal-email"))
        for match in (SECRET_ASSIGNMENT.finditer(line) if pure.suffix.lower() in {".json", ".yaml", ".yml", ".toml", ".ini", ".properties", ".py", ".java"} or pure.name == ".env.example" else []):
            if pure.suffix.lower() in {".py", ".java"} and (all(v is None for v in match.groups()[1:3]) or not re.match(r"^\s*[A-Z_][A-Z0-9_]*\s*[:=]", line, re.I)):
                continue
            value = next((v for v in match.groups()[1:] if v is not None), "").strip()
            synthetic = "test" in pure.parts or any("test" in part or part.startswith("e2e") for part in pure.parts)
            placeholder = not value or value.startswith(("$", "<")) or value in {"...", "***", "key", "KEY", "test", "dummy", "None", "null"}
            if not synthetic and not placeholder and not re.fullmatch(r"[A-Z_]+", value):
                findings.append((path, i, "literal-credential"))
    return findings

def run_git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], stderr=subprocess.DEVNULL)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    findings = []
    count = 0
    try:
        paths = run_git("ls-files", "-z").decode().split("\0")
    except subprocess.CalledProcessError:
        paths = []
    if not any(paths):
        paths = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")
                 if p.is_file() and not any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts)
                 and (not p.name.startswith(".env") or p.name == ".env.example")]

    for path in filter(None, paths):
        file = ROOT / path
        if file.is_file():
            findings.extend(inspect(file.read_bytes(), path))
            count += 1
    if args.history:
        try:
            objects = run_git("rev-list", "--objects", "--all").decode().splitlines()
        except subprocess.CalledProcessError:
            parser.error("--history requires a Git repository")
        batch = subprocess.Popen(["git", "-C", str(ROOT), "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        assert batch.stdin and batch.stdout
        for obj in objects:
            fields = obj.split(" ", 1)
            oid = fields[0]
            path = fields[1] if len(fields) > 1 else "<commit-metadata>"
            batch.stdin.write((oid + "\n").encode())
            batch.stdin.flush()
            header = batch.stdout.readline().decode().split()
            data = batch.stdout.read(int(header[2]))
            batch.stdout.read(1)
            if header[1] == "blob":
                findings.extend(inspect(data, path))
            elif header[1] == "commit":
                findings.extend(inspect(data.split(b"\n\n", 1)[-1], "<commit-message:" + oid[:12] + ">"))
        batch.stdin.close()
        batch.wait()
        for row in run_git("log", "--all", "--format=%an%x09%ae%n%cn%x09%ce").decode().splitlines():
            name, email = row.split("\t", 1)
            if not email.endswith(("@users.noreply.github.com", "@contributors.invalid")):
                findings.append(("<commit-metadata>", 1, "private-author-email"))
        for ref in run_git("for-each-ref", "--format=%(refname)").decode().splitlines():
            findings.extend(inspect(ref.encode(), "<git-reference>"))
    for path, line, rule in sorted(set(findings)):
        print(f"[FAIL] {path}:{line} ({rule})")
    if findings:
        return 1
    print(f"[ OK ] Repository: {count} files; history={'checked' if args.history else 'not requested'}.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
