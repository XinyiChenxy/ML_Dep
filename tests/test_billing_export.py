from types import SimpleNamespace

import pytest

from scripts.billing_export import build_query, find_standard_export_table


def test_billing_query_filters_project_and_both_lab_labels():
    query = build_query("my-project.billing.gcp_billing_export_v1_ABC")
    assert "project.id = @project_id" in query
    assert "label.key = 'course' AND label.value = 'itcs355'" in query
    assert "label.key = 'lab' AND label.value = '5'" in query
    assert "UNNEST(credits)" in query


def test_billing_query_rejects_identifier_injection():
    with pytest.raises(ValueError, match="Invalid BigQuery table"):
        build_query("project.dataset.table`; DROP TABLE x; --")


def test_export_table_discovery_ignores_unrelated_tables():
    client = SimpleNamespace(list_tables=lambda _: [
        SimpleNamespace(table_id="notes"),
        SimpleNamespace(table_id="gcp_billing_export_v1_123"),
    ])
    assert find_standard_export_table(client, "p", "d") == (
        "p.d.gcp_billing_export_v1_123"
    )


def test_export_table_discovery_explains_console_prerequisite():
    client = SimpleNamespace(list_tables=lambda _: [])
    with pytest.raises(RuntimeError, match="Enable Standard usage cost export"):
        find_standard_export_table(client, "p", "d")
