#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT_DIR / "docs"
CHANGES_DIR = DOCS_DIR / "changes"
AI_HANDOFF_LOG = DOCS_DIR / "AI_HANDOFF_LOG.md"

CORE_DOCS = [
    "00_AI_HANDOFF_PROTOCOL.md",
    "01_SYSTEM_ARCHITECTURE.md",
    "02_BUSINESS_DOMAIN.md",
    "03_DATA_CONTRACTS.md",
    "04_OPS_AND_DEV.md",
    "05_LLM_KEY_SECURITY.md",
    "06_CHANGE_MANAGEMENT.md",
    "07_PENDING_TODO.md",
    "08_DOCS_GOVERNANCE.md",
    "AI_QUICK_START.md",
    "AI_HANDOFF_LOG.md",
]

CHANGE_CARD_RE = re.compile(
    r"^(MOD|REQ|INV|CFG|STG|REL)-\d{8}(?:-\d{2}|-v\d+\.\d+\.\d+)-[a-z0-9][a-z0-9-]*\.md$"
)
ALLOWED_CHANGE_SUPPORT_FILES = {
    "README.md",
    "TEMPLATE_CHANGE_CARD.md",
}


@dataclass
class CheckResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def info(self, message: str) -> None:
        self.infos.append(message)


def read_text(path: Path, result: CheckResult) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        result.error(f"缺少文件: {path.relative_to(ROOT_DIR)}")
    except OSError as exc:
        result.error(f"无法读取文件 {path.relative_to(ROOT_DIR)}: {exc}")
    return ""


def check_core_docs(result: CheckResult) -> None:
    if not DOCS_DIR.is_dir():
        result.error("缺少 docs/ 目录。")
        return

    missing = [name for name in CORE_DOCS if not (DOCS_DIR / name).is_file()]
    if missing:
        result.error("核心文档保留集缺失: " + ", ".join(missing))
    else:
        result.info(f"核心文档保留集完整: {len(CORE_DOCS)} / {len(CORE_DOCS)}")


def check_pending_todo(result: CheckResult) -> None:
    pending = DOCS_DIR / "07_PENDING_TODO.md"
    if pending.is_file():
        result.info("07_PENDING_TODO.md 存在")
    else:
        result.error("缺少 docs/07_PENDING_TODO.md")


def iter_change_files() -> Iterable[Path]:
    if not CHANGES_DIR.is_dir():
        return []
    return sorted(path for path in CHANGES_DIR.iterdir() if path.is_file())


def check_change_cards(result: CheckResult) -> None:
    if not CHANGES_DIR.is_dir():
        result.error("缺少 docs/changes/ 目录。")
        return

    files = list(iter_change_files())
    invalid = [
        path.name
        for path in files
        if path.name not in ALLOWED_CHANGE_SUPPORT_FILES
        and not CHANGE_CARD_RE.match(path.name)
    ]
    total = len(files)
    result.info(f"docs/changes 文件数: {total}")
    if invalid:
        sample = ", ".join(invalid[:5])
        more = "" if len(invalid) <= 5 else f" 等 {len(invalid)} 个"
        result.warning(
            "docs/changes 存在不符合正式命名的文件，当前按历史遗留处理为 warning: "
            f"{sample}{more}"
        )
    else:
        result.info("docs/changes 文件命名全部符合 <TYPE>-YYYYMMDD-NN-slug.md")


def split_handoff_blocks(text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    current_title: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current_title is not None:
                blocks.append((current_title, "\n".join(current_lines).strip()))
            current_title = line[3:].strip()
            current_lines = []
        elif current_title is not None:
            current_lines.append(line)

    if current_title is not None:
        blocks.append((current_title, "\n".join(current_lines).strip()))
    return blocks


def check_ai_handoff(result: CheckResult) -> None:
    text = read_text(AI_HANDOFF_LOG, result)
    if not text:
        return

    blocks = split_handoff_blocks(text)
    if not blocks:
        result.error("AI_HANDOFF_LOG.md 未找到任何日志块（缺少 '## 日期 | 作者' 段落）。")
        return

    title, body = blocks[0]
    normalized = body.replace("：", ":")
    fields = {
        "Task ID": bool(re.search(r"(^|\n)-\s*Task ID\s*:", normalized)),
        "CAP": bool(re.search(r"(^|\n)-\s*CAP\s*:", normalized)),
        "结论": bool(re.search(r"(^|\n)-\s*结论\s*:", normalized)),
        "风险或阻塞": bool(
            re.search(r"(^|\n)-\s*(风险|阻塞)\s*:", normalized)
        ),
        "链接": bool(re.search(r"(^|\n)-\s*链接\s*:", normalized)),
    }
    missing = [name for name, present in fields.items() if not present]

    if missing:
        result.warning(
            "AI_HANDOFF_LOG 最新日志块字段不完整，当前按 warning 处理: "
            f"{title} 缺少 {', '.join(missing)}"
        )
    else:
        result.info(f"AI_HANDOFF_LOG 最新日志块结构完整: {title}")

    if len(blocks) > 8:
        result.warning(
            f"AI_HANDOFF_LOG 当前有 {len(blocks)} 个日志块，可能已超出最近 1~2 个版本窗口。"
        )
    else:
        result.info(f"AI_HANDOFF_LOG 日志块数量: {len(blocks)}")


def check_git_worktrees(result: CheckResult) -> None:
    try:
        completed = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        result.warning(f"无法执行 git worktree list --porcelain: {exc}")
        return

    if completed.returncode != 0:
        stderr = completed.stderr.strip() or "未知错误"
        result.warning(f"git worktree list --porcelain 执行失败: {stderr}")
        return

    worktrees: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                worktrees.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value.strip()
    if current:
        worktrees.append(current)

    if not worktrees:
        result.warning("未解析到任何 git worktree 信息。")
        return

    result.info(f"git worktree 数量: {len(worktrees)}")
    for item in worktrees:
        path = item.get("worktree", "<unknown>")
        branch = item.get("branch", "(detached)")
        head = item.get("HEAD", "")
        short_head = head[:12] if head else "unknown"
        result.info(f"worktree: {path} | branch: {branch} | HEAD: {short_head}")


def print_section(title: str, items: list[str]) -> None:
    print(title)
    if not items:
        print("  - none")
        return
    for item in items:
        print(f"  - {item}")


def main() -> int:
    result = CheckResult()

    check_core_docs(result)
    check_change_cards(result)
    check_ai_handoff(result)
    check_pending_todo(result)
    check_git_worktrees(result)

    print("Governance Check Summary")
    print(f"  errors: {len(result.errors)}")
    print(f"  warnings: {len(result.warnings)}")
    print(f"  infos: {len(result.infos)}")
    print()
    print_section("[ERROR]", result.errors)
    print()
    print_section("[WARNING]", result.warnings)
    print()
    print_section("[INFO]", result.infos)

    if result.errors:
        print("\nResult: FAIL")
        return 1

    if result.warnings:
        print("\nResult: PASS_WITH_WARNINGS")
    else:
        print("\nResult: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
