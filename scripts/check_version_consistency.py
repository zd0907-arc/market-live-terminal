#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def extract_readme_version(text: str) -> str:
    match = re.search(r"v(\d+\.\d+\.\d+)", text)
    if not match:
        raise ValueError("README.md 标题中未找到 vX.Y.Z 版本号")
    return match.group(1)


def extract_ts_version(text: str) -> str:
    match = re.search(r"APP_VERSION\s*=\s*'([^']+)'", text)
    if not match:
        raise ValueError("src/version.ts 中未找到 APP_VERSION")
    return match.group(1)


def extract_backend_version(text: str) -> str:
    match = re.search(r'version="([^"]+)"', text)
    if not match:
        raise ValueError("backend/app/main.py 中未找到 FastAPI version")
    return match.group(1)


def main() -> int:
    versions = {
        "package.json": json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"],
        "README.md": extract_readme_version((ROOT / "README.md").read_text(encoding="utf-8")),
        "src/version.ts": extract_ts_version((ROOT / "src/version.ts").read_text(encoding="utf-8")),
        "backend/app/main.py": extract_backend_version((ROOT / "backend/app/main.py").read_text(encoding="utf-8")),
    }

    target = next(iter(versions.values()))
    mismatches = {path: version for path, version in versions.items() if version != target}

    print("Version snapshot:")
    for path, version in versions.items():
        print(f"  - {path}: {version}")

    if mismatches:
        print("\nVersion mismatch detected:", file=sys.stderr)
        for path, version in mismatches.items():
            print(f"  - {path}: {version} (expected {target})", file=sys.stderr)
        return 1

    print(f"\nOK: all version markers are aligned at {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
