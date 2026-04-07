from pathlib import Path


ROOT = Path(r"F:\x-ui")


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
