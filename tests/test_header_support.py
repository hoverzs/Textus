from pathlib import Path


APP_SOURCE = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")


def test_support_block_is_inside_the_existing_header() -> None:
    header_start = APP_SOURCE.index('<div class="main-card header-card">')
    header_end = APP_SOURCE.index("if not background_file:", header_start)
    header_markup = APP_SOURCE[header_start:header_end]

    assert '<section class="header-support"' in header_markup
    assert "<aside" not in header_markup
    assert header_markup.index('class="header-text"') < header_markup.index('class="header-support"')
    assert "A Textus támogatása" in header_markup
    assert (
        "A Textus ingyenesen használható, fenntartását és fejlesztését saját "
        "forrásból fedezem. Ha hasznosnak találod, önkéntes hozzájárulásoddal "
        "segítheted a folytatást."
    ) in header_markup
    assert "Támogatom a Textust" in header_markup
    assert "{support_icon_html}" in header_markup
    assert "Textus_support_icon.webp" in APP_SOURCE


def test_support_link_opens_ko_fi_safely_in_a_new_tab() -> None:
    assert (
        '<a class="header-support-link" href="https://ko-fi.com/textus" '
        'target="_blank" rel="noopener noreferrer">'
    ) in APP_SOURCE


def test_support_layout_has_desktop_and_responsive_rules() -> None:
    assert "minmax(280px, 0.8fr)" not in APP_SOURCE
    assert "grid-template-columns: 148px minmax(0, 1fr)" in APP_SOURCE
    assert "@media (max-width: 1024px)" in APP_SOURCE
    assert "@media (max-width: 640px)" in APP_SOURCE
    assert ".header-card .header-support-text" in APP_SOURCE
    assert "width: 100%;" in APP_SOURCE
    assert "background: linear-gradient(180deg, #557cab, #3b628e);" in APP_SOURCE
    block = APP_SOURCE[APP_SOURCE.index(".header-support {{"):]
    block = block[: block.index("}}")]
    assert "border: none;" in block
    assert "background: none;" in block
    assert "box-shadow: none;" in block


def test_header_keeps_only_brand_and_compact_meta_line() -> None:
    assert "APP_SCRIPTURE" not in APP_SOURCE
    assert "2Timóteus 3,16" not in APP_SOURCE
    assert '<div class="header-meta">' in APP_SOURCE
    assert '<span class="header-meta-separator" aria-hidden="true"></span>' in APP_SOURCE
    assert ".header-meta-separator {{\n        display: none;" in APP_SOURCE
