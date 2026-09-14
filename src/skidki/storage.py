"""Хранилище: SQLite одним файлом. История цен — отрезками, а не снимками.

Отрезок — период, когда позиция стояла по одной цене с одним наличием и
наблюдалась без перерыва. Обход с той же ценой продлевает отрезок, а не
добавляет строку: ~16 тыс. позиций × 12 обходов в сутки давали бы ~6 млн
строк за месяц, а база уходит в git после каждого обхода.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import DB_PATH
from .models import Product

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    identity    TEXT PRIMARY KEY,
    shop        TEXT NOT NULL,
    title       TEXT NOT NULL,
    brand       TEXT,
    category    TEXT,
    url         TEXT NOT NULL,
    grp         TEXT,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS spans (
    id          INTEGER PRIMARY KEY,
    identity    TEXT    NOT NULL,
    first_seen  TEXT    NOT NULL,
    last_seen   TEXT    NOT NULL,
    price       INTEGER NOT NULL,
    old_price   INTEGER,
    in_stock    INTEGER NOT NULL,
    stock_note  TEXT
);
CREATE INDEX IF NOT EXISTS idx_spans_identity ON spans(identity, last_seen);

-- Найденные находки. delivered_at = NULL — найдена, но не доставлена:
-- дедупликацию расходуют только доставленные (урок gpu-deals).
CREATE TABLE IF NOT EXISTS alerts (
    identity      TEXT PRIMARY KEY,
    signal        TEXT    NOT NULL,
    alerted_at    TEXT    NOT NULL,
    alerted_price INTEGER NOT NULL,
    delivered_at  TEXT
);

-- Очередь находок: всё найденное ждёт здесь, пока не уйдёт в Telegram.
-- Обход показывает до max_alerts самых глубоких, остальное — следующими
-- обходами. Без очереди находки сверх лимита терялись: в следующем обходе
-- скидка уже не «новая» (ночь 2026-09-14: 92 находки, доставлено 32).
-- signals — JSON сигналов вердикта: карточка из очереди не беднее свежей.
CREATE TABLE IF NOT EXISTS queue (
    identity  TEXT PRIMARY KEY,
    found_at  TEXT    NOT NULL,
    price     INTEGER NOT NULL,
    signals   TEXT    NOT NULL
);

-- Группы уведомлений, выключенные владельцем (кнопки /groups).
CREATE TABLE IF NOT EXISTS muted (
    grp  TEXT PRIMARY KEY
);

-- Итоги обходов: нужны, чтобы заметить молча сломавшийся парсер.
CREATE TABLE IF NOT EXISTS crawls (
    id          INTEGER PRIMARY KEY,
    started_at  TEXT    NOT NULL,
    shop        TEXT    NOT NULL,
    item_count  INTEGER NOT NULL,
    ok          INTEGER NOT NULL,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_crawls_shop ON crawls(shop, started_at);
"""

# Перерыв в наблюдениях длиннее — новый отрезок: позиция пропадала из
# каталога, и цена за перерыв неизвестна. Обход раз в 2 часа плюс запас на
# задержки расписания GitHub.
GAP = timedelta(hours=6)


def now() -> datetime:
    return datetime.now(UTC)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def _dt(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


@dataclass(frozen=True)
class Span:
    first_seen: datetime
    last_seen: datetime
    price: int
    in_stock: bool
    old_price: int | None = None


def _migrate(conn: sqlite3.Connection) -> None:
    """Разовые миграции существующих баз."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(products)")}
    if "grp" not in columns:
        conn.execute("ALTER TABLE products ADD COLUMN grp TEXT")


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    target = path or DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    # timeout: слушатель бота пишет в базу, пока обход держит транзакцию.
    conn = sqlite3.connect(target, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_products(
    conn: sqlite3.Connection, products: Iterable[Product], at: datetime | None = None
) -> int:
    """Записывает наблюдения обхода: продлевает или открывает отрезки."""
    moment = at or now()
    stamp = _iso(moment)
    count = 0
    for product in products:
        conn.execute(
            """INSERT INTO products (identity, shop, title, brand, category, url, grp,
                                     first_seen, last_seen)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(identity) DO UPDATE SET
                   title = excluded.title, brand = excluded.brand,
                   category = excluded.category, url = excluded.url,
                   grp = COALESCE(excluded.grp, products.grp),
                   last_seen = excluded.last_seen""",
            (product.identity, product.shop, product.title, product.brand,
             product.category, product.url, product.group, stamp, stamp),
        )
        last = conn.execute(
            """SELECT id, last_seen, price, in_stock FROM spans WHERE identity = ?
               ORDER BY last_seen DESC, id DESC LIMIT 1""",
            (product.identity,),
        ).fetchone()
        if (
            last is not None
            and last["price"] == product.price
            and bool(last["in_stock"]) == product.in_stock
            and moment - _dt(last["last_seen"]) <= GAP
        ):
            conn.execute(
                "UPDATE spans SET last_seen = ?, old_price = ?, stock_note = ? WHERE id = ?",
                (stamp, product.old_price, product.stock_note, last["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO spans (identity, first_seen, last_seen, price, old_price,
                                      in_stock, stock_note)
                   VALUES (?,?,?,?,?,?,?)""",
                (product.identity, stamp, stamp, product.price, product.old_price,
                 int(product.in_stock), product.stock_note),
            )
        count += 1
    return count


def _span(row: sqlite3.Row) -> Span:
    return Span(
        _dt(row["first_seen"]), _dt(row["last_seen"]), row["price"], bool(row["in_stock"]),
        row["old_price"],
    )


def history(conn: sqlite3.Connection, identity: str, since: datetime) -> list[Span]:
    """Отрезки позиции, задевающие окно с `since`, от старых к новым."""
    rows = conn.execute(
        """SELECT first_seen, last_seen, price, old_price, in_stock FROM spans
           WHERE identity = ? AND last_seen >= ?
           ORDER BY first_seen, id""",
        (identity, _iso(since)),
    )
    return [_span(row) for row in rows]


def last_span(conn: sqlite3.Connection, identity: str) -> Span | None:
    row = conn.execute(
        """SELECT first_seen, last_seen, price, old_price, in_stock FROM spans WHERE identity = ?
           ORDER BY last_seen DESC, id DESC LIMIT 1""",
        (identity,),
    ).fetchone()
    return _span(row) if row else None


def current_deals(
    conn: sqlite3.Connection,
    min_pct: float,
    min_price: int,
    max_pct: float,
    limit: int,
    shop: str | None = None,
) -> list[Product]:
    """Самые глубокие скидки магазина по последнему наблюдению каждой позиции."""
    rows = conn.execute(
        """SELECT p.identity, p.shop, p.title, p.brand, p.category, p.url, p.grp,
                  s.price, s.old_price, s.in_stock, s.stock_note
           FROM products p
           JOIN spans s ON s.id = (
               SELECT id FROM spans WHERE identity = p.identity
               ORDER BY last_seen DESC, id DESC LIMIT 1)
           WHERE s.in_stock = 1 AND s.old_price > s.price AND s.price >= ?
                 AND (? IS NULL OR p.shop = ?)
                 AND (s.old_price - s.price) * 100.0 / s.old_price BETWEEN ? AND ?
           ORDER BY (s.old_price - s.price) * 1.0 / s.old_price DESC
           LIMIT ?""",
        (min_price, shop, shop, min_pct, max_pct, limit),
    ).fetchall()
    return [_product(row) for row in rows]


def _product(row: sqlite3.Row) -> Product:
    """Позиция по строке products + её последнего отрезка."""
    return Product(
        shop=row["shop"],
        sku=row["identity"].split(":", 1)[1],
        title=row["title"],
        price=row["price"],
        url=row["url"],
        brand=row["brand"],
        category=row["category"],
        old_price=row["old_price"],
        in_stock=bool(row["in_stock"]),
        stock_note=row["stock_note"],
        group=row["grp"],
    )


def last_alert(conn: sqlite3.Connection, identity: str, since: datetime) -> int | None:
    """Цена последнего ДОСТАВЛЕННОГО алерта не старше `since`.

    Недоставленные (сбой Telegram) дедупликацию не расходуют. Алерт старше окна
    тоже не считается: цена могла вернуться вверх и снова упасть до той же суммы.
    """
    row = conn.execute(
        """SELECT alerted_price FROM alerts
           WHERE identity = ? AND delivered_at IS NOT NULL AND alerted_at >= ?""",
        (identity, _iso(since)),
    ).fetchone()
    return row["alerted_price"] if row else None


def record_alert(
    conn: sqlite3.Connection, identity: str, signal: str, price: int, at: datetime | None = None
) -> None:
    """Фиксирует НАЙДЕННУЮ находку: delivered_at = NULL до подтверждения доставки."""
    conn.execute(
        """INSERT INTO alerts (identity, signal, alerted_at, alerted_price, delivered_at)
           VALUES (?,?,?,?,NULL)
           ON CONFLICT(identity) DO UPDATE SET signal = excluded.signal,
                                               alerted_at = excluded.alerted_at,
                                               alerted_price = excluded.alerted_price,
                                               delivered_at = NULL""",
        (identity, signal, _iso(at or now()), price),
    )


def mark_alerts_delivered(
    conn: sqlite3.Connection, identities: list[str], at: datetime | None = None
) -> None:
    stamp = _iso(at or now())
    conn.executemany(
        "UPDATE alerts SET delivered_at = ? WHERE identity = ? AND delivered_at IS NULL",
        [(stamp, identity) for identity in identities],
    )


@dataclass(frozen=True)
class Queued:
    product: Product  # текущее состояние позиции, а не на момент находки
    signals: str
    found_at: datetime


def enqueue(
    conn: sqlite3.Connection, identity: str, price: int, signals: str, at: datetime | None = None
) -> None:
    """Ставит находку в очередь (повторная находка обновляет её)."""
    conn.execute(
        """INSERT INTO queue (identity, found_at, price, signals) VALUES (?,?,?,?)
           ON CONFLICT(identity) DO UPDATE SET found_at = excluded.found_at,
                                               price = excluded.price,
                                               signals = excluded.signals""",
        (identity, _iso(at or now()), price, signals),
    )


def dequeue(conn: sqlite3.Connection, identity: str) -> None:
    conn.execute("DELETE FROM queue WHERE identity = ?", (identity,))


def take_queue(conn: sqlite3.Connection, since: datetime) -> list[Queued]:
    """Живые находки очереди: не старше `since`, товар в наличии и не подорожал.

    Протухшие и потерявшие силу удаляются: карточка «скидка −30%» на товар,
    который с тех пор подорожал или кончился, — дезинформация.
    """
    conn.execute("DELETE FROM queue WHERE found_at < ?", (_iso(since),))
    rows = conn.execute(
        """SELECT q.identity, q.price AS queued_price, q.signals, q.found_at,
                  p.shop, p.title, p.brand, p.category, p.url, p.grp,
                  s.price, s.old_price, s.in_stock, s.stock_note
           FROM queue q
           JOIN products p ON p.identity = q.identity
           JOIN spans s ON s.id = (
               SELECT id FROM spans WHERE identity = q.identity
               ORDER BY last_seen DESC, id DESC LIMIT 1)"""
    ).fetchall()
    alive: list[Queued] = []
    for row in rows:
        if not row["in_stock"] or row["price"] > row["queued_price"]:
            dequeue(conn, row["identity"])
            continue
        alive.append(Queued(_product(row), row["signals"], _dt(row["found_at"])))
    return alive


def queue_size(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM queue").fetchone()[0]


def muted_groups(conn: sqlite3.Connection) -> set[str]:
    return {row["grp"] for row in conn.execute("SELECT grp FROM muted")}


def toggle_group(conn: sqlite3.Connection, grp: str) -> bool:
    """Переключает группу уведомлений; True — теперь выключена."""
    if conn.execute("SELECT 1 FROM muted WHERE grp = ?", (grp,)).fetchone():
        conn.execute("DELETE FROM muted WHERE grp = ?", (grp,))
        return False
    conn.execute("INSERT INTO muted (grp) VALUES (?)", (grp,))
    return True


def record_crawl(
    conn: sqlite3.Connection,
    shop: str,
    item_count: int,
    ok: bool,
    error: str | None = None,
    at: datetime | None = None,
) -> None:
    conn.execute(
        "INSERT INTO crawls (started_at, shop, item_count, ok, error) VALUES (?,?,?,?,?)",
        (_iso(at or now()), shop, item_count, int(ok), error),
    )


def previous_item_count(conn: sqlite3.Connection, shop: str) -> int | None:
    """Сколько позиций дал магазин в прошлый успешный обход."""
    row = conn.execute(
        """SELECT item_count FROM crawls WHERE shop = ? AND ok = 1 AND item_count > 0
           ORDER BY started_at DESC, id DESC LIMIT 1""",
        (shop,),
    ).fetchone()
    return row["item_count"] if row else None


def last_crawl_ok(conn: sqlite3.Connection, shop: str) -> bool | None:
    row = conn.execute(
        "SELECT ok FROM crawls WHERE shop = ? ORDER BY started_at DESC, id DESC LIMIT 1",
        (shop,),
    ).fetchone()
    return None if row is None else bool(row["ok"])


def last_successful_crawl(conn: sqlite3.Connection, shop: str) -> datetime | None:
    row = conn.execute(
        """SELECT started_at FROM crawls WHERE shop = ? AND ok = 1
           ORDER BY started_at DESC, id DESC LIMIT 1""",
        (shop,),
    ).fetchone()
    return _dt(row["started_at"]) if row else None


def prune(conn: sqlite3.Connection, days: int, at: datetime | None = None) -> int:
    """Удаляет историю старше окна; возвращает число удалённых отрезков."""
    since = _iso((at or now()) - timedelta(days=days))
    removed = conn.execute("DELETE FROM spans WHERE last_seen < ?", (since,)).rowcount
    conn.execute("DELETE FROM products WHERE last_seen < ?", (since,))
    conn.execute("DELETE FROM alerts WHERE identity NOT IN (SELECT identity FROM products)")
    conn.execute("DELETE FROM queue WHERE identity NOT IN (SELECT identity FROM products)")
    conn.execute("DELETE FROM crawls WHERE started_at < ?", (since,))
    return removed


def compact(path: Path | None = None) -> int:
    """VACUUM после retention; возвращает освободившиеся байты.

    Без него файл навсегда сохраняет размер своего пика. Отдельной функцией:
    VACUUM нельзя выполнить внутри транзакции `connect()`.
    """
    target = path or DB_PATH
    if not target.exists():
        return 0
    before = target.stat().st_size
    conn = sqlite3.connect(target, isolation_level=None)
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()
    return max(before - target.stat().st_size, 0)
