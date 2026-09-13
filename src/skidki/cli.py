"""Точка входа: skidki crawl | watchdog."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import settings
from .crawler import run_once, send_watchdog
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skidki", description="Мониторинг скидок mechta.kz и evrika.com"
    )
    parser.add_argument(
        "command",
        choices=("crawl", "watchdog"),
        help="crawl — обход и уведомления; watchdog — тревога, если обходы перестали приходить",
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

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    notifier = _build_notifier(args.console)

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
