"""Живая проверка нового парсера evrika: дерево + 3 категории + страница 2."""
import asyncio
import sys

sys.path.insert(0, "src")

from skidki.browser import open_context
from skidki.config import EVRIKA_ROOTS, settings
from skidki.parsers import evrika


async def main() -> None:
    async with open_context() as context:
        page = await evrika._new_page(context)
        root_id, root_slug = EVRIKA_ROOTS[0]
        html = await evrika._load(page, evrika.category_url(root_id, root_slug), settings.page_timeout_ms)
        tree = evrika.menu_tree(evrika.flight_state(html))
        leaves = evrika.leaf_categories(tree, {cid for cid, _ in EVRIKA_ROOTS})
        groups = evrika.category_groups(tree, evrika.__dict__.get("x", {}) or __import__("skidki.config", fromlist=["EVRIKA_GROUPS"]).EVRIKA_GROUPS)
        names = {n["id"]: n.get("name") for n in tree}
        print(f"tree={len(tree)} leaves={len(leaves)}")
        for slug in ["smart-chasy", "smartfony", "holodilniki"]:
            leaf = next(((cid, s) for cid, s in leaves if s == slug), None)
            if not leaf:
                print(slug, "not found"); continue
            cid, s = leaf
            h = await evrika._load(page, evrika.category_url(cid, s), settings.page_timeout_ms)
            items, last_page = evrika.parse_page(h, group=groups.get(cid), category=names.get(cid))
            discounted = [p for p in items if p.old_price]
            out_of_stock = [p for p in items if not p.in_stock]
            print(f"{s}: items={len(items)} last_page={last_page} group={groups.get(cid)} "
                  f"со скидкой={len(discounted)} нет в наличии={len(out_of_stock)}")
            for p in items[:2]:
                print(f"   {p.sku} {p.title[:48]!r} {p.price} (было {p.old_price}) img={'да' if p.image else 'нет'}")
        # страница 2: карточки тоже SSR?
        cid = next(cid for cid, s in leaves if s == "smartfony")
        h2 = await evrika._load(page, evrika.category_url(cid, "smartfony", 2), settings.page_timeout_ms)
        items2, last2 = evrika.parse_page(h2, category=names.get(cid))
        print(f"smartfony page=2: items={len(items2)} last_page={last2}")
        await page.close()


asyncio.run(main())
