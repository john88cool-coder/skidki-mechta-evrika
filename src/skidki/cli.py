"""Точка входа: skidki crawl | watchdog | sample | bot."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import settings
from .crawler import run_once, send_sample, send_watchdog
from .notify import ConsoleNotifier, Notifier, TelegramNotifier
from .parsers import REGISTRY


def _build_notifier(force_console: bool) -> Notifier:
    if force_console or not (settings.telegram_token and settings.telegram_chat_id):
        if not force_console:
            print(
                "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы — вывод в консоль",
                file=sys.stderr,
            )
        return ConsoleNotifier()
    return TelegramNotifier(settings.telegram_token, settings.telegram_chat_id)


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    # httpx на INFO пишет полный URL запроса, а в URL Bot API — токен бота
    # (так токен попал в вывод первого `skidki sample`, 2026-09-13).
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skidki",
        description="Мониторинг скидок mechta.kz, evrika.com, shop.kz, sulpak.kz, technodom.kz, alser.kz",
    )
    parser.add_argument(
        "command",
        choices=("crawl", "watchdog", "sample", "bot", "export"),
        help=(
            "crawl — обход и уведомления; watchdog — тревога, если обходы перестали приходить; "
            "sample — пример сводки на текущих скидках из базы; "
            "bot — слушатель кнопок и команд Telegram (группы уведомлений); "
            "export — JSON-срез для веб-панели на GitHub Pages"
        ),
    )
    parser.add_argument("--shop", action="append", choices=sorted(REGISTRY), help="только эти магазины")
    parser.add_argument("--console", action="store_true", help="печатать вместо отправки в Telegram")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=6.0,
        metavar="N",
        help="watchdog: тревожить, если последний успешный обход старше N часов",
    )
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)

    if args.command == "bot":
        if not (settings.telegram_token and settings.telegram_chat_id):
            print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы — слушать нечего", file=sys.stderr)
            return 1
        from .bot import run

        run(settings.telegram_token, settings.telegram_chat_id)
        return 0

    notifier = _build_notifier(args.console)

    if args.command == "export":
        from .export import export_for_web

        target = export_for_web()
        logging.info("срез для веб-панели: %s", target)
        return 0

    if args.command == "sample":
        send_sample(notifier, shops=args.shop)
        return 0

    if args.command == "watchdog":
        if not send_watchdog(notifier, max_age_hours=args.max_age_hours, shops=args.shop):
            logging.info("все обходы свежи — тревоги нет")
        return 0

    count = run_once(notifier, shops=args.shop)
    if count == 0:
        logging.info("находок нет")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
