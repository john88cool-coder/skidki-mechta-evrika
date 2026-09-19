"""Сквозная проверка: фикстуры → БД → экспорт JSON (с миниатюрами).

    python probe/export_smoke.py                  # временная база, отчёт в консоль
    python probe/export_smoke.py web/static/data  # срез прямо в панель (для визуальной проверки)

Создаёт базу из позиций, разобранных из фикстур всех шести магазинов,
экспортирует срез и печатает статистику по картинкам.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from skidki import export, storage  # noqa: E402
from skidki.parsers import alser, evrika, mechta, shopkz, sulpak, technodom  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


def collect() -> list:
    products = []
    products += mechta.parse(json.loads((FIX / "mechta_products.json").read_text(encoding="utf-8")))
    products += evrika.parse_products(
        evrika.next_data((FIX / "evrika_category.html").read_text(encoding="utf-8"))
    )[0]
    products += technodom.parse(
        json.loads((FIX / "technodom_products.json").read_text(encoding="utf-8"))
    )
    products += shopkz.parse_cards(
        (FIX / "shopkz_listing.html").read_text(encoding="utf-8"), "phones"
    )
    products += sulpak.parse_blocks(
        (FIX / "sulpak_listing.html").read_text(encoding="utf-8"), "phones"
    )
    products += alser.parse(
        json.loads((FIX / "alser_catalog.json").read_text(encoding="utf-8")), "computers"
    )
    return products


def main() -> None:
    products = collect()
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    tmp = tempfile.TemporaryDirectory() if target is None else None
    out = Path(tmp.name) / "data" if tmp else ROOT / target

    db = Path(tmp.name) / "smoke.sqlite3" if tmp else Path(tempfile.mkdtemp()) / "smoke.sqlite3"
    with storage.connect(db) as conn:
        storage.save_products(conn, products)
        export.export_dashboard(conn, out)

    data = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    deals = data["deals"]
    with_image = [d for d in deals if d["product"].get("image")]
    print(f"позиций собрано: {len(products)}")
    print(f"с картинкой в модели: {sum(1 for p in products if p.image)}")
    print(f"скидок в срезе: {len(deals)}, из них с картинкой: {len(with_image)}")
    for deal in deals[:8]:
        image = deal["product"].get("image") or "—"
        print(f"  {deal['product']['shop']:<10} {image[:88]}")

    if tmp:
        tmp.cleanup()


if __name__ == "__main__":
    main()