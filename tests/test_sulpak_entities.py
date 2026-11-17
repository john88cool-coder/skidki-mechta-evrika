from pathlib import Path

from skidki.parsers import sulpak

FIXTURES = Path(__file__).parent / "fixtures"


def test_sulpak_unescapes_html_entities_in_title_and_brand():
    html = (FIXTURES / "sulpak_listing.html").read_text(encoding="utf-8")
    html = html.replace(
        'data-name="Смартфон Huawei Pura 90s Pro 12/512GB Max Blaze Purple"',
        'data-name="Телевизор Dreame 86&quot; Aura &#x2B; Copilot&amp;PC"',
        1,
    )
    html = html.replace('data-brand="', 'data-brand="B&amp;O ', 1)
    first = sulpak.parse_blocks(html, "tv")[0]
    assert first.title == 'Телевизор Dreame 86" Aura + Copilot&PC'
    assert first.brand.startswith("B&O ")
