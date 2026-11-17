"""Tests for the model tools, through an MCP client and a fake API."""

import httpx2
import pytest

from tests.helpers import FakeApi, call_tool, error_text, ok, sent

pytestmark = pytest.mark.anyio

RUNS = "/api/bbm/runs"

VERSION = {
    "id": "v1",
    "version_id": "v1",
    "bbm_id": "m1",
    "model_id": "m1",
    "version_number": 3,
    "status": "released",
    "checksum": "c" * 64,
    "schema_version": "bbm.v1",
    "payload": {
        "nodes": [
            {"semantic_key": "rain", "states": ["yes", "no"]},
            {"semantic_key": "wet_grass", "states": ["yes", "no"]},
        ],
        "edges": [{"source_key": "rain", "target_key": "wet_grass"}],
        "factors": [
            {
                "node_key": "rain",
                "parent_keys": [],
                "distribution": [{"given": {}, "p": {"yes": 0.2, "no": 0.8}}],
            }
        ],
        "bindings": [],
    },
    "validation": [{"check_name": "acyclic", "passed": True}],
}


def receipt(**fields: object) -> dict[str, object]:
    """A run's receipt as the API returns it."""
    return {
        "run_id": "r1",
        "mode": "posterior",
        "status": "succeeded",
        "error": None,
        "evidence": {"wet_grass": "yes"},
        "interventions": {},
        "posteriors": {
            "rain": {"yes": 0.7, "no": 0.3},
            "wet_grass": {"yes": 1.0, "no": 0.0},
        },
        "diagnostics": {"assignments_scored": 2},
        "version_id": "v1",
        "model_id": "m1",
        "version_number": 3,
        "checksum": "c" * 64,
        "engine_version": "enumerate.log.v2",
        "request_key": "k1",
        "created_at": "2026-11-12T20:00:00Z",
        "finished_at": "2026-11-12T20:00:01Z",
        **fields,
    }


async def test_run_model_sends_the_version_evidence_and_request_key(api: FakeApi):
    routes, requests = api
    routes["POST", RUNS] = ok(receipt(replayed=False))

    result = await call_tool(
        "run_model", version_id="v1", evidence={"wet_grass": "yes"}, request_key="k1"
    )

    assert sent(requests, "POST", RUNS) == {
        "version_id": "v1",
        "evidence": {"wet_grass": "yes"},
        "request_key": "k1",
    }
    assert result.structured_content == receipt(replayed=False)


async def test_run_model_without_a_request_key_returns_the_key_crowdsmart_made(
    api: FakeApi,
):
    routes, requests = api
    made = receipt(evidence={}, request_key="made-by-crowdsmart", replayed=False)
    routes["POST", RUNS] = ok(made)

    result = await call_tool("run_model", version_id="v1")

    assert sent(requests, "POST", RUNS) == {"version_id": "v1", "evidence": {}}
    assert result.structured_content == made


async def test_run_model_returns_a_replayed_receipt_unchanged(api: FakeApi):
    routes, _ = api
    routes["POST", RUNS] = ok(receipt(replayed=True))

    result = await call_tool(
        "run_model", version_id="v1", evidence={"wet_grass": "yes"}, request_key="k1"
    )

    assert result.structured_content == receipt(replayed=True)


@pytest.mark.parametrize(
    ("status", "detail"),
    [
        (422, "Evidence/interventions have probability zero under this BBM"),
        (422, "Unknown nodes in evidence/interventions: ['snow']"),
        (400, "This request key was already used for a different run"),
        (400, "Inference is allowed only on released BBM versions"),
        (404, "BBM version not found"),
        (409, "This model belongs to a Knowledge Agent's adaptive learning"),
    ],
)
async def test_run_model_errors_reach_the_client(
    api: FakeApi, status: int, detail: str
):
    routes, _ = api
    routes["POST", RUNS] = httpx2.Response(status, json={"detail": detail})

    result = await call_tool("run_model", version_id="v1", evidence={"rain": "no"})

    assert error_text(result).endswith(f"CrowdSmart API error {status}: {detail}")


async def test_get_model_version_returns_the_version_unchanged(api: FakeApi):
    routes, requests = api
    routes["GET", "/api/bbm/versions/v1"] = ok(VERSION)

    result = await call_tool("get_model_version", version_id="v1")

    assert [r.url.path for r in requests] == ["/api/bbm/versions/v1"]
    assert result.structured_content == VERSION


async def test_get_model_run_returns_the_receipt_unchanged(api: FakeApi):
    routes, requests = api
    routes["GET", f"{RUNS}/r1"] = ok(receipt())

    result = await call_tool("get_model_run", run_id="r1")

    assert [r.url.path for r in requests] == [f"{RUNS}/r1"]
    assert result.structured_content == receipt()
