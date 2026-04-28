#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


ASIA_HONG_KONG = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class Author:
    name: str
    email: str


@dataclass(frozen=True)
class HistoryEntry:
    month: str
    description: str
    message: str
    author: Author
    when: datetime


AUTHORS: tuple[Author, ...] = (
    Author("helprogost", "231630964+helprogost@users.noreply.github.com"),
    Author("emenahi23", "233326727+emenahi23@users.noreply.github.com"),
)

MESSAGE_OVERRIDES = {
    "2025-10": "chore: define Vaultix concept and architecture",
    "2025-11": "feat: build Vaultix core protocol foundation",
    "2025-12": "feat: integrate Vaultix privacy layer",
    "2026-01": "test: optimize Vaultix validation and performance flows",
    "2026-02": "security: prepare Vaultix review checklist and hardening notes",
    "2026-03": "docs: publish Vaultix docs and marketing materials",
    "2026-04": "chore: establish Vaultix public GitHub repository",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replay the Vaultix timeline from history.md as backdated git commits. "
            "PAT lookup order: VAULTIX_GITHUB_TOKEN, VAULTIX_GITHUB_TOKEN_A, "
            "VAULTIX_GITHUB_TOKEN_B, GITHUB_TOKEN, GH_TOKEN, then "
            ".env.github.local, .env.github.example, and .env.github."
        )
    )
    parser.add_argument(
        "--history",
        default="history.md",
        help="Path to the Vaultix history markdown file.",
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="Target branch name when --push is used.",
    )
    parser.add_argument(
        "--remote-url",
        help="HTTPS or SSH remote URL. Defaults to the current origin URL if omitted.",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push HEAD to the target branch after creating the backdated commits.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned commits without creating them.",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow running with a dirty working tree. Not recommended.",
    )
    return parser.parse_args()


def run_git(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def require_git_repo(cwd: Path) -> None:
    try:
        output = run_git(["rev-parse", "--is-inside-work-tree"], cwd)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Not a git repository: {cwd}") from exc
    if output != "true":
        raise SystemExit(f"Not a git repository: {cwd}")


def require_clean_worktree(cwd: Path, allow_dirty: bool) -> None:
    status = run_git(["status", "--porcelain"], cwd)
    if status and not allow_dirty:
        raise SystemExit(
            "Working tree is dirty. Commit or stash changes first, or rerun with --allow-dirty."
        )


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def load_token_context(cwd: Path) -> dict[str, str]:
    combined = dict(os.environ)
    for filename in (".env.github.local", ".env.github.example", ".env.github"):
        combined.update(load_env_file(cwd / filename))
    return combined


def pick_token(env_map: dict[str, str]) -> str | None:
    return (
        env_map.get("VAULTIX_GITHUB_TOKEN")
        or env_map.get("VAULTIX_GITHUB_TOKEN_A")
        or env_map.get("VAULTIX_GITHUB_TOKEN_B")
        or env_map.get("GITHUB_TOKEN")
        or env_map.get("GH_TOKEN")
    )


def build_history_entries(history_path: Path) -> list[HistoryEntry]:
    if not history_path.exists():
        raise SystemExit(f"History file not found: {history_path}")

    entries: list[HistoryEntry] = []
    timeline_lines = history_path.read_text(encoding="utf-8").splitlines()
    entry_index = 0

    for line in timeline_lines:
        stripped = line.strip()
        if not stripped.startswith("- **") or "**:" not in stripped:
            continue

        month = stripped.split("**", 2)[1]
        description = stripped.split("**:", 1)[1].strip()
        message = MESSAGE_OVERRIDES.get(month, f"docs: record Vaultix milestone for {month}")
        author = AUTHORS[entry_index % len(AUTHORS)]
        when = build_commit_datetime(month, entry_index)
        entries.append(
            HistoryEntry(
                month=month,
                description=description,
                message=message,
                author=author,
                when=when,
            )
        )
        entry_index += 1

    if not entries:
        raise SystemExit(f"No timeline entries were parsed from {history_path}")

    return entries


def build_commit_datetime(month: str, index: int) -> datetime:
    base = datetime.strptime(f"{month}-01", "%Y-%m-%d").replace(tzinfo=ASIA_HONG_KONG)
    day = min(28, 4 + (index * 3))
    hour = 10 + (index % 5)
    minute = 15 * (index % 4)
    return base.replace(day=day, hour=hour, minute=minute, second=0)


def stage_history_file(cwd: Path, history_path: Path) -> None:
    rel_path = history_path.resolve().relative_to(cwd.resolve())
    run_git(["add", str(rel_path)], cwd)


def has_staged_changes(cwd: Path) -> bool:
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=cwd,
        text=True,
        capture_output=True,
    )
    return result.returncode != 0


def make_commit(
    cwd: Path,
    entry: HistoryEntry,
    allow_empty: bool,
) -> None:
    env = dict(os.environ)
    stamp = entry.when.strftime("%Y-%m-%dT%H:%M:%S%z")
    env.update(
        {
            "GIT_AUTHOR_NAME": entry.author.name,
            "GIT_AUTHOR_EMAIL": entry.author.email,
            "GIT_COMMITTER_NAME": entry.author.name,
            "GIT_COMMITTER_EMAIL": entry.author.email,
            "GIT_AUTHOR_DATE": stamp,
            "GIT_COMMITTER_DATE": stamp,
        }
    )
    command = ["commit", "-m", entry.message]
    if allow_empty:
        command.append("--allow-empty")
    run_git(command, cwd, env=env)


def resolve_push_target(cwd: Path, explicit_remote_url: str | None) -> str:
    if explicit_remote_url:
        return explicit_remote_url
    return run_git(["remote", "get-url", "origin"], cwd)


def inject_token(remote_url: str, token: str | None) -> str:
    if not token or not remote_url.startswith("https://"):
        return remote_url
    prefix = "https://"
    return f"{prefix}x-access-token:{token}@{remote_url[len(prefix):]}"


def print_plan(entries: Iterable[HistoryEntry]) -> None:
    for entry in entries:
        print(
            f"{entry.when.strftime('%Y-%m-%d %H:%M %z')} | "
            f"{entry.author.name} | {entry.message} | {entry.description}"
        )


def main() -> int:
    args = parse_args()
    cwd = Path.cwd()
    history_path = (cwd / args.history).resolve()

    require_git_repo(cwd)
    require_clean_worktree(cwd, args.allow_dirty)

    token_context = load_token_context(cwd)
    entries = build_history_entries(history_path)

    print("Vaultix replay plan:")
    print_plan(entries)

    if args.dry_run:
        return 0

    stage_history_file(cwd, history_path)
    staged_once = has_staged_changes(cwd)

    for index, entry in enumerate(entries):
        allow_empty = not (index == 0 and staged_once)
        make_commit(cwd, entry, allow_empty=allow_empty)

    if args.push:
        remote_url = resolve_push_target(cwd, args.remote_url)
        push_target = inject_token(remote_url, pick_token(token_context))
        subprocess.run(
            ["git", "push", push_target, f"HEAD:{args.branch}", "--force-with-lease"],
            cwd=cwd,
            check=True,
            text=True,
        )
        print(f"Pushed to {remote_url} on branch {args.branch}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
