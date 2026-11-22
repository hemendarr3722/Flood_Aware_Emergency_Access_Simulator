"""
scripts/secret_scan.py — Phase 8 automated secret scanner.
Scans all tracked code files for potential secrets, private keys, API tokens,
and ensures Supabase 'resume' and 'Clipzo' references are strictly forbidden.
"""
import os
import re
import sys

PATTERNS = [
    (r"(?i)(password|secret|api_key|access_token|private_key)\s*=\s*['\"][^'\"]{8,}['\"]", "Hardcoded potential secret"),
    (r"(?i)postgresql://[a-zA-Z0-9_]+:[a-zA-Z0-9_]+@[a-zA-Z0-9.-]+:[0-9]+/[a-zA-Z0-9_]+", "Hardcoded full DB connection string with password"),
    (r"-----BEGIN [A-Z ]+ PRIVATE KEY-----", "Raw private key block"),
    (r"(?i)eyJhbGciOi[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+", "JWT token"),
]

ALLOWED_FILES = {
    "scripts/secret_scan.py",
    ".env.example",
}

FORBIDDEN_WORDS = [
    ("resume", "Reference to forbidden Supabase project 'resume'"),
    ("Clipzo", "Reference to forbidden Supabase project 'Clipzo'"),
]

def scan_file(filepath: str) -> list[str]:
    issues = []
    # Skip virtual environments, git, pycache, dist, node_modules
    norm = filepath.replace("\\", "/")
    if any(skip in norm for skip in [".venv", ".git", "__pycache__", "node_modules", "dist", ".pytest_cache"]):
        return []

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return []

    # Check for forbidden projects 'resume' and 'Clipzo' (except in guidelines/documentation instructing not to touch them)
    # Check if forbidden terms appear in code or configuration (exclude master_prompt, IMPLEMENTATION_STATUS, docs)
    is_doc = any(norm.endswith(ext) for ext in [".md", ".txt"])
    if not is_doc:
        for word, msg in FORBIDDEN_WORDS:
            if word in content:
                issues.append(f"CRITICAL VIOLATION: {msg} found in {filepath}")

    for pat, desc in PATTERNS:
        # Allow default local dev credentials like 'flood_local_dev_only' in tests
        matches = re.finditer(pat, content)
        for m in matches:
            matched_str = m.group(0)
            if "flood_local_dev_only" in matched_str or "example" in matched_str.lower():
                continue
            issues.append(f"{desc} in {filepath}: {matched_str[:40]}...")

    return issues

def main():
    root = os.getcwd()
    all_issues = []
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in [".py", ".ts", ".tsx", ".js", ".json", ".sql", ".env"]:
                fpath = os.path.join(dirpath, fname)
                relpath = os.path.relpath(fpath, root)
                if relpath.replace("\\", "/") not in ALLOWED_FILES:
                    issues = scan_file(fpath)
                    all_issues.extend(issues)

    if all_issues:
        print("SECRET SCAN FAILED:")
        for iss in all_issues:
            print(f"  [!] {iss}")
        sys.exit(1)
    else:
        print("SECRET SCAN PASSED: Zero leaked credentials or forbidden references found.")

if __name__ == "__main__":
    main()
