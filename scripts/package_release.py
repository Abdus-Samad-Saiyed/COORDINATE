"""Pristine Release Packaging Script for Campus Nexus.

Builds a deployment bundle exclusively from git-tracked files.
Strictly inspects and fails if any local secrets, SQLite databases,
bytecode, dumps, or sensitive credential files are detected.
"""

import os
import sys
import subprocess
import zipfile
import re
from pathlib import Path

# Regex rules for prohibited release artifacts
FORBIDDEN_RULES = [
    (r'(^|/)\.env($|\.local$|\.prod$)', 'Active .env file'),
    (r'(^|/)secrets_local\.py$', 'Local python secrets file'),
    (r'\.sqlite3$', 'SQLite database file'),
    (r'\.pyc$', 'Compiled Python bytecode'),
    (r'(^|/)__pycache__($|/)', 'Python cache directory'),
    (r'campus_secrets', 'Secrets documentation'),
    (r'debug_accounts\.md$', 'Debug accounts documentation'),
    (r'test_report\.json$', 'Test report data file'),
    (r'project_dump', 'Raw project dump file'),
]

def build_clean_release(output_zip: str = 'campus_nexus_release.zip'):
    root_dir = Path(__file__).resolve().parent.parent
    os.chdir(root_dir)

    print("=" * 60)
    print("CAMPUS NEXUS RELEASE PACKAGING & ARTIFACT HYGIENE CHECK")
    print("=" * 60)

    # 1. Fetch tracked files via git
    try:
        result = subprocess.run(
            ['git', 'ls-files'],
            capture_output=True,
            text=True,
            check=True
        )
        tracked_files = [line.strip().replace('\\', '/') for line in result.stdout.splitlines() if line.strip()]
    except Exception as e:
        print(f"[FATAL] Failed to list git-tracked files: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Total git-tracked files discovered: {len(tracked_files)}")

    # 2. Verify no forbidden patterns exist in tracked files
    violations = []
    for f in tracked_files:
        for pattern, desc in FORBIDDEN_RULES:
            if re.search(pattern, f, re.IGNORECASE):
                violations.append((f, desc))

    if violations:
        print("\n[CRITICAL SECURITY FAILURE] Tracked files contain prohibited secrets/artifacts:", file=sys.stderr)
        for f, desc in violations:
            print(f"  - {f} (Rule violation: {desc})", file=sys.stderr)
        print("\nRelease packaging aborted to prevent credential/data leakage.", file=sys.stderr)
        sys.exit(1)

    print("[PASS] Release hygiene check passed: Zero prohibited files in git tracking.")

    # 3. Create zip archive
    out_path = root_dir / output_zip
    print(f"[*] Packaging clean archive into {out_path}...")

    with zipfile.ZipFile(out_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for rel_path in tracked_files:
            abs_path = root_dir / rel_path
            if abs_path.is_file():
                zf.write(abs_path, arcname=rel_path)

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"[SUCCESS] Release package created successfully: {output_zip} ({size_mb:.2f} MB)")
    print("=" * 60)

if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else 'campus_nexus_release.zip'
    build_clean_release(target)
