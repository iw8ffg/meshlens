"""Icone del sito: index.html e cartella public della UI."""
from pathlib import Path

WEB = Path(__file__).parents[2] / "web"


def test_index_links_favicon_and_apple_touch_icon():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert '<link rel="icon" href="/favicon.ico" sizes="any" />' in html
    assert '<link rel="icon" href="/favicon.svg" type="image/svg+xml" />' in html
    assert '<link rel="apple-touch-icon" href="/apple-touch-icon.png" />' in html


def test_public_icons_exist():
    for name in ("favicon.svg", "favicon.ico", "apple-touch-icon.png"):
        assert (WEB / "public" / name).is_file()


def test_favicon_svg_is_copy_of_logo():
    assert (WEB / "public" / "favicon.svg").read_bytes() == \
        (WEB.parent / "docs" / "img" / "logo.svg").read_bytes()


def test_favicon_ico_header():
    assert (WEB / "public" / "favicon.ico").read_bytes()[:4] == b"\x00\x00\x01\x00"


def test_apple_touch_icon_is_180_px_wide():
    png = (WEB / "public" / "apple-touch-icon.png").read_bytes()
    assert png[12:16] == b"IHDR" and int.from_bytes(png[16:20], "big") == 180
