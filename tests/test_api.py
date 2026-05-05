"""End-to-end API tests.

Builds a real slice of pipeline state (raw → normalized → scored) under a
unique source label, exercises every endpoint against it, and tears the data
back down. This catches integration issues that pure-unit tests miss
(SQLAlchemy joins, Pydantic serialization, route wiring).
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from api.app import create_app
from db.models import RawRecord
from db.session import get_session
from ingest.runner import run_ingest
from ingest.sources.csv_file import CSVFileIngester
from normalize.runner import run_normalize
from normalize.sources.sample_us import SampleUSNormalizer
from score.runner import run_score


SAMPLE_CSV = Path(__file__).parent.parent / "data" / "sample_us_unclaimed.csv"


@pytest.fixture(scope="module")
def seeded_pipeline():
    """Run the full pipeline against the sample CSV once for the module."""
    test_source = f"api_test_{uuid.uuid4().hex[:8]}"

    ingester = CSVFileIngester(path=SAMPLE_CSV, source=test_source)
    ingest_result = run_ingest(ingester)

    run_normalize({test_source: SampleUSNormalizer()})
    run_score()

    yield {"source": test_source, "batch_id": ingest_result.file_batch_id}

    with get_session() as session:
        session.execute(
            delete(RawRecord).where(
                RawRecord.file_batch_id == ingest_result.file_batch_id
            )
        )


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


def test_list_leads_returns_paginated_results(client, seeded_pipeline):
    r = client.get("/api/leads", params={"state": "TX", "limit": 10})
    assert r.status_code == 200
    body = r.json()

    assert "items" in body and "total" in body
    assert body["limit"] == 10
    assert body["offset"] == 0
    assert len(body["items"]) <= 10
    assert body["total"] >= len(body["items"])

    for item in body["items"]:
        assert item["state"] == "TX"
        for key in ("id", "owner_name", "score", "priority", "exported_to_crm"):
            assert key in item


def test_list_leads_orders_by_score_desc(client, seeded_pipeline):
    r = client.get("/api/leads", params={"limit": 50})
    assert r.status_code == 200
    scores = [item["score"] for item in r.json()["items"]]
    assert scores == sorted(scores, reverse=True)


def test_list_leads_filters_by_priority(client, seeded_pipeline):
    r = client.get("/api/leads", params={"priority": "high", "limit": 200})
    assert r.status_code == 200
    body = r.json()
    assert all(item["priority"] == "high" for item in body["items"])


def test_list_leads_filters_by_min_amount(client, seeded_pipeline):
    r = client.get("/api/leads", params={"min_amount": "10000", "limit": 200})
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert Decimal(item["claim_amount"]) >= Decimal("10000")


def test_list_leads_pagination_offset(client, seeded_pipeline):
    page1 = client.get("/api/leads", params={"limit": 5, "offset": 0}).json()
    page2 = client.get("/api/leads", params={"limit": 5, "offset": 5}).json()
    if page1["total"] >= 10:
        page1_ids = {item["id"] for item in page1["items"]}
        page2_ids = {item["id"] for item in page2["items"]}
        assert page1_ids.isdisjoint(page2_ids)


def test_get_lead_detail(client, seeded_pipeline):
    listed = client.get("/api/leads", params={"limit": 1}).json()
    assert listed["items"], "expected at least one seeded lead"
    lead_id = listed["items"][0]["id"]

    r = client.get(f"/api/leads/{lead_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == lead_id
    assert "score_breakdown" in body
    assert isinstance(body["score_breakdown"], dict)
    assert "address_line1" in body
    assert "source" in body


def test_get_lead_detail_404_for_unknown_id(client):
    fake_id = uuid.uuid4()
    r = client.get(f"/api/leads/{fake_id}")
    assert r.status_code == 404


def test_get_lead_detail_422_for_malformed_id(client):
    r = client.get("/api/leads/not-a-uuid")
    assert r.status_code == 422


def test_stats_endpoint(client, seeded_pipeline):
    r = client.get("/api/stats")
    assert r.status_code == 200
    body = r.json()

    assert body["total_leads"] >= 70  # the seeded sample has 70 unique leads
    assert set(body["by_priority"].keys()) == {"high", "medium", "low"}
    sum_priorities = sum(body["by_priority"].values())
    assert sum_priorities == body["total_leads"]
    assert Decimal(body["total_claim_amount"]) > 0
    assert body["exported"] + body["pending_export"] == body["total_leads"]
