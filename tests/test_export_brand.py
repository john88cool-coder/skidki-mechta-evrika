from skidki import export
from skidki.models import Product


def test_brand_is_stripped_in_export():
    padded = Product(shop="shopkz", sku="1", title="t", price=1, url="u", brand="Oscal ")
    blank = Product(shop="shopkz", sku="2", title="t", price=1, url="u", brand="  ")
    assert export._product_to_dict(padded)["brand"] == "Oscal"
    assert export._product_to_dict(blank)["brand"] is None
