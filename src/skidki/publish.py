"""Публикация среза домашнего ПК на GitHub Pages.

Гибрид 2026-09-18: mechta обходится с домашнего ПК (Cloudflare режет IP
дата-центров), остальные магазины — в Actions. Облачный срез панели mechta
не видел вовсе: на сайте она горела «требует проверки», хотя данные были.
Теперь ПК после обхода кладёт свой срез в `data/local/` ветки gh-pages, а
панель подмешивает его к облачному (web/src/lib/stores/data.svelte.ts).

Ветка правится через отдельный worktree (`.pages/`), рабочая копия
репозитория не трогается. Облачный обход публикует с `keep_files: true`,
поэтому `data/local/` он не удаляет.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from .config import ROOT
from .export import export_for_web

log = logging.getLogger("skidki.publish")

BRANCH = "gh-pages"
WORKTREE = ROOT / ".pages"
TARGET = Path("data") / "local"


def _git(*args: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=check, capture_output=True, text=True, encoding="utf-8"
    )


def _ensure_worktree() -> None:
    _git("fetch", "--quiet", "origin", BRANCH)
    if not (WORKTREE / ".git").exists():
        _git("worktree", "prune")
        _git("worktree", "add", "--force", "--detach", str(WORKTREE), f"origin/{BRANCH}")
    _git("checkout", "--quiet", "--detach", f"origin/{BRANCH}", cwd=WORKTREE)
    _git("reset", "--quiet", "--hard", f"origin/{BRANCH}", cwd=WORKTREE)


def publish_local(db_path: Path | None = None, attempts: int = 3) -> bool:
    """Выгружает срез локальной базы и публикует его. True — опубликовано."""
    for attempt in range(1, attempts + 1):
        _ensure_worktree()
        out = WORKTREE / TARGET
        if out.exists():
            shutil.rmtree(out)
        export_for_web(db_path, out)
        _git("add", "--all", str(TARGET), cwd=WORKTREE)
        if not _git("status", "--porcelain", str(TARGET), cwd=WORKTREE).stdout.strip():
            log.info("срез не изменился — публиковать нечего")
            return False
        _git("commit", "--quiet", "-m", "data: срез домашнего ПК", cwd=WORKTREE)
        pushed = _git("push", "--quiet", "origin", f"HEAD:{BRANCH}", cwd=WORKTREE, check=False)
        if pushed.returncode == 0:
            log.info("срез опубликован в %s/%s", BRANCH, TARGET.as_posix())
            return True
        # Облачный обход успел запушить свой срез — берём свежую ветку и повторяем.
        log.warning("push отклонён (попытка %d/%d)", attempt, attempts)
    raise RuntimeError("не удалось опубликовать срез: ветка gh-pages всё время менялась")
