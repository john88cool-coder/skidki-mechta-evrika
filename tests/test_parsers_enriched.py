from skidki.parsers import alser, evrika, mechta, shopkz, sulpak, technodom


def test_mechta_extracts_rating_and_reviews():
    raw = {
        "products": [
            {
                "id": 10,
                "code": "88990",
                "name": "Наушники Sony WH-1000XM5",
                "slug": "sony-wh-1000xm5",
                "availability": "available",
                "prices": {"basePrice": 199990, "finalPrice": 149990},
                "metrics": {"brand": "SONY", "category": "Наушники"},
                "rating": {"averageRating": 4.8, "reviewsCount": 26},
                "images": ["https://pi.mdev.kz/1.jpg"],
            }
        ]
    }
    items = mechta.parse(raw, group="audio")
    assert len(items) == 1
    assert items[0].rating == 4.8
    assert items[0].reviews_count == 26


def test_technodom_normalizes_100_scale_rating_and_stock_notes():
    raw = {
        "payload": [
            {
                "sku": "273887",
                "title": "Смарт-часы Huawei Watch GT4",
                "uri": "smart-chasy-gt4",
                "price": 59990,
                "old_price": 99990,
                "brand": "HUAWEI",
                "categories_ru": ["Смартфоны и гаджеты", "Смарт часы"],
                "rating": 98,
                "reviews": 77,
                "is_preorder": False,
                "showcase": True,
                "images": ["abc"],
            }
        ]
    }
    items = technodom.parse(raw, group="phones")
    assert len(items) == 1
    assert items[0].rating == 4.9
    assert items[0].reviews_count == 77
    assert items[0].stock_note == "на витрине"


def test_evrika_guards_equal_old_price_and_infers_brand():
    # Разметка карточек — как в реальном SSR (классы, которые матчат regexes
    # CARD_ANCHOR/CURRENT_PRICE/OLD_PRICE; см. fixtures/evrika_category.html).
    html = (
        '<script>self.__next_f.push([1,"{\\"state\\":{\\"data\\":1}}"])</script>'
        '<div class="productCard-ui">'
        '<a class="productCard__titleOfProduct" href="/catalog/smartfony/samsung-s24/p55001"><span>Смартфон Samsung Galaxy S24 256GB</span></a>'
        '<span class="productCard__currentPrice ">350 000 ₸</span>'
        '<span class="productCard__oldPrice ">350 000 ₸</span>'
        "</div>"
        '<div class="productCard-ui">'
        '<a class="productCard__titleOfProduct" href="/catalog/smartfony/apple-16/p55002"><span>Смартфон Apple iPhone 16 128GB</span></a>'
        '<span class="productCard__currentPrice ">420 000 ₸</span>'
        '<span class="productCard__oldPrice ">499 990 ₸</span>'
        "</div>"
    )
    items, _ = evrika.parse_page(html, group="phones", category="smartfony")
    assert len(items) == 2
    assert items[0].old_price is None
    assert items[0].brand == "Samsung"
    assert items[1].old_price == 499_990
    assert items[1].brand == "Apple"


def test_sulpak_passes_category_slug():
    html = (
        '<div class="product__item product__item-js" data-code="771" '
        'data-name="Пылесос Dyson V15" data-price="329990" data-brand="Dyson">'
        '<a href="/g/dyson-v15">Dyson</a>'
        "</div>"
    )
    items = sulpak.parse_blocks(html, group="home", category="piylesosiy")
    assert len(items) == 1
    assert items[0].category == "piylesosiy"


def test_alser_handles_camel_case_old_price_breadcrumbs_and_showcase_note():
    raw = {
        "data": {
            "breadcrumbs": [{"title": "Каталог"}, {"title": "Смартфоны"}],
            "products": [
                {
                    "sku": "1537980",
                    "title": "Смартфон Xiaomi 14T",
                    "price": 219990,
                    "oldPrice": 269990,
                    "brand": "Xiaomi",
                    "stocks_quantity": 3,
                    "non_showcase": True,
                    "rating": 5,
                    "feedbackCount": 12,
                    "link_url": "https://alser.kz/p/xiaomi-14t",
                }
            ],
        }
    }
    items = alser.parse(raw, group="phones", category="smartfony")
    assert len(items) == 1
    got = items[0]
    assert got.old_price == 269_990
    assert got.category == "Смартфоны"
    assert got.in_stock is False
    assert got.stock_note == "на витрине"
    assert got.rating == 5.0
    assert got.reviews_count == 12


def test_shopkz_unescapes_entities_extracts_mpn_and_blocks_bitrix_static():
    html = (
        """<div data-product='{&quot;product_id&quot;:&quot;109988&quot;,&quot;item_name&quot;:&quot;Ноутбук ASUS &amp; ROG&quot;,&quot;item_brand&quot;:&quot;ASUS&quot;,&quot;item_category&quot;:&quot;Ноутбуки&quot;,&quot;item_variant&quot;:&quot;G614JV-N4071&quot;,&quot;price&quot;:699990,&quot;dimension3&quot;:&quot;available&quot;}'>"""
        '<link itemprop="url" href="/offer/asus-rog/">'
        '<div class="old_price"><span>799 990 ₸</span></div>'
        '<div class="current_price"><span>699 990 ₸</span></div>'
        "</div>"
    )
    items = shopkz.parse_cards(html, group="computers")
    assert len(items) == 1
    assert items[0].title == "Ноутбук ASUS & ROG"
    assert items[0].mpn == "G614JV-N4071"
    assert shopkz._should_abort_url("https://shop.kz/bitrix/cache/css/s1/template.css") is True
    assert shopkz._should_abort_url("https://mc.yandex.ru/metrika/tag.js") is True
    assert shopkz._should_abort_url("https://shop.kz/cdn-cgi/challenge-platform/scripts/main.js") is False
    assert shopkz._should_abort_url("https://shop.kz/offers/noutbuki/") is False
