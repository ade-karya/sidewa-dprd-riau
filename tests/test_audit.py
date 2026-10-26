"""Pengujian log audit dan ekspor."""

from tests.conftest import login


def test_audit_page_and_export(seeded_client):
    test_client, _ = seeded_client
    login(test_client, "superadmin", "Riau#Admin2026")

    response = test_client.get("/audit")
    assert response.status_code == 200
    assert "Log audit" in response.text

    response = test_client.get("/audit/ekspor.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")
    assert "Waktu" in response.text or "Aktor" in response.text
