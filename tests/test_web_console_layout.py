from pathlib import Path


ROOT = Path(r"F:\x-ui")


def test_console_pages_extend_shared_console_layout() -> None:
    templates = ROOT / "xui_port_pool_generator_web" / "templates"
    page_names = [
        "dashboard.html",
        "sources.html",
        "groups.html",
        "generate.html",
        "reports.html",
        "runtime_config.html",
    ]

    for name in page_names:
        text = (templates / name).read_text(encoding="utf-8")
        assert '{% extends "console_base.html" %}' in text
        assert '<aside class="sidebar">' not in text


def test_console_base_owns_sidebar_navigation() -> None:
    text = (
        ROOT
        / "xui_port_pool_generator_web"
        / "templates"
        / "console_base.html"
    ).read_text(encoding="utf-8")

    assert 'class="sidebar"' in text
    assert 'href="/dashboard"' in text
    assert "{{ active_nav }}" in text


def test_base_template_uses_local_assets_only() -> None:
    text = (
        ROOT / "xui_port_pool_generator_web" / "templates" / "base.html"
    ).read_text(encoding="utf-8")

    assert 'lang="zh-CN"' in text
    assert "unpkg.com" not in text
    assert "fonts.googleapis.com" not in text
    assert "fonts.gstatic.com" not in text


def test_dense_tables_use_scroll_wrappers() -> None:
    templates = ROOT / "xui_port_pool_generator_web" / "templates"
    dashboard = (templates / "dashboard.html").read_text(encoding="utf-8")
    groups = (templates / "groups.html").read_text(encoding="utf-8")
    reports = (templates / "reports.html").read_text(encoding="utf-8")

    assert dashboard.count('class="table-scroll"') >= 1
    assert groups.count('class="table-scroll"') >= 2
    assert reports.count('class="table-scroll"') >= 2


def test_css_wraps_runtime_paths() -> None:
    text = (
        ROOT / "xui_port_pool_generator_web" / "static" / "app.css"
    ).read_text(encoding="utf-8")

    assert ".path-value" in text
    assert "overflow-wrap: anywhere;" in text


def test_groups_template_uses_wide_rule_fields_and_narrow_port_fields() -> None:
    text = (
        ROOT / "xui_port_pool_generator_web" / "templates" / "groups.html"
    ).read_text(encoding="utf-8")

    assert 'class="groups-table data-table"' in text
    assert 'textarea class="rule-field" name="group_filter"' in text
    assert 'textarea class="rule-field" name="group_exclude"' in text
    assert 'class="port-field"' in text
    assert "新增一行" in text


def test_reports_template_marks_issue_panel_for_independent_scrolling() -> None:
    text = (
        ROOT / "xui_port_pool_generator_web" / "templates" / "reports.html"
    ).read_text(encoding="utf-8")

    assert 'class="panel issues-panel"' in text


def test_css_keeps_sidebar_visible_and_limits_issue_panel_height() -> None:
    text = (
        ROOT / "xui_port_pool_generator_web" / "static" / "app.css"
    ).read_text(encoding="utf-8")

    assert "position: sticky;" in text
    assert "height: 100vh;" in text
    assert ".issues-panel" in text
    assert "overflow: auto;" in text
    assert "grid-template-columns: 220px 1fr;" in text
