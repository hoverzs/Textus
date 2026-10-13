from pathlib import Path


APP_SOURCE = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")


def test_support_block_is_inside_the_existing_header() -> None:
    header_start = APP_SOURCE.index('<div class="main-card header-card">')
    header_end = APP_SOURCE.index("if not background_file:", header_start)
    header_markup = APP_SOURCE[header_start:header_end]

    assert '<aside class="header-support"' in header_markup
    assert "A Textus támogatása" in header_markup
    assert (
        "A Textus ingyenesen használható, fenntartását és fejlesztését saját "
        "forrásból fedezem. Ha hasznosnak találod, önkéntes hozzájárulásoddal "
        "segítheted a folytatást."
    ) in header_markup
    assert "Támogatom a Textust" in header_markup


def test_support_link_opens_ko_fi_safely_in_a_new_tab() -> None:
    assert (
        '<a class="header-support-link" href="https://ko-fi.com/textus" '
        'target="_blank" rel="noopener noreferrer">'
    ) in APP_SOURCE


def test_support_layout_has_desktop_and_responsive_rules() -> None:
    assert "grid-template-columns: 148px minmax(360px, 1.2fr) minmax(280px, 0.8fr)" in APP_SOURCE
    assert "@media (max-width: 1024px)" in APP_SOURCE
    assert "@media (max-width: 640px)" in APP_SOURCE
    assert ".header-card .header-support-text" in APP_SOURCE
    assert "width: min(100%, 46rem);" in APP_SOURCE
    assert "width: 100%;" in APP_SOURCE
