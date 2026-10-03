"""Генерация tests/fixtures/evrika_menutree.html — реальное дерево категорий
evrika из RSC-потока сохранённой корневой страницы (probe/evrika_page.html)."""
import json
import sys

sys.path.insert(0, "src")
from skidki.parsers import evrika

html = open("probe/evrika_page.html", encoding="utf-8").read()
tree = evrika.menu_tree(evrika.flight_state(html))
print("tree nodes:", len(tree))

query = {
    "state": {"data": {"data": tree}},
    "queryKey": ["categories/menutree", "ru", 0, "shared", "v4.0.0", "web"],
}
row = "3:[" + json.dumps(
    ["$", "$L1", None, {"state": {"mutations": [], "queries": [query]}}],
    ensure_ascii=False,
    separators=(",", ":"),
) + "]"

# строкаflight внутри push: JSON-строка с экранированными кавычками
push_arg = json.dumps([1, row], ensure_ascii=False)
fixture = (
    '<!DOCTYPE html><html lang="ru"><head><title>fixture</title></head><body>'
    "<script>self.__next_f.push(" + push_arg + ")</script></body></html>\n"
)
with open("tests/fixtures/evrika_menutree.html", "w", encoding="utf-8") as f:
    f.write(fixture)
print("written:", len(fixture), "bytes")
# самопроверка
again = evrika.menu_tree(evrika.flight_state(fixture))
print("roundtrip nodes:", len(again), "first:", again[0]["id"], again[0]["slug"])
