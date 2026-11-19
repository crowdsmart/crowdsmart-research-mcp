"""Tests for a KMA's past versions, its runs and its history, through an MCP client and a fake API."""

import httpx2
import pytest

from tests.helpers import FakeApi, call_tool, error_text, ok, sent

pytestmark = pytest.mark.anyio

KMA = "/api/knowledge-agents/a1/kma/v2"
DOMAINS = "/api/kma/v2/domains"


def receipt(**fields: object) -> dict[str, object]:
    """A run's receipt as the API returns it."""
    return {
        "schema": "kma.model_run.v1",
        "run_id": "f" * 32,
        "agent_id": "a1",
        "caller": "user-1",
        "request_key": "k1",
        "request": {
            "perspective": "p_main",
            "observed": {"rate": "high"},
            "version": 2,
        },
        "definition": {"version": 2, "content_sha256": "d" * 64},
        "model": {"perspective": "p_main", "version": "b1.r1", "sha256": "m" * 64},
        "outcome": "decision",
        "engine": "enumerate.log.v2",
        "prior": {"hike": 0.3, "hold": 0.7},
        "posteriors": {"decision": {"hike": 0.6, "hold": 0.4}, "rate": {"high": 1.0}},
        "scope": "The published model alone with the given observations: ...",
        "content_sha256": "c" * 64,
        "at": "2026-11-18 20:00:00+00:00",
        **fields,
    }


async def test_get_kma_model_reads_a_past_version(api: FakeApi):
    routes, requests = api
    view: dict[str, object] = {
        "published": True,
        "version": 1,
        "domain": "rates",
        "perspectives": [],
    }
    routes["GET", f"{KMA}/model"] = ok(view)

    result = await call_tool("get_kma_model", agent_id="a1", version=1)

    assert [(r.url.path, dict(r.url.params)) for r in requests] == [
        (f"{KMA}/model", {"version": "1"})
    ]
    assert result.structured_content == view


async def test_get_kma_model_without_a_version_reads_the_latest(api: FakeApi):
    routes, requests = api
    routes["GET", f"{KMA}/model"] = ok({"published": False, "perspectives": []})

    _ = await call_tool("get_kma_model", agent_id="a1")

    assert [dict(r.url.params) for r in requests] == [{}]


async def test_run_kma_model_sends_only_what_is_given(api: FakeApi):
    routes, requests = api
    made = receipt(request_key="made-by-crowdsmart", replayed=False)
    routes["POST", f"{KMA}/runs"] = ok(made)

    result = await call_tool("run_kma_model", agent_id="a1", perspective="p_main")

    assert sent(requests, "POST", f"{KMA}/runs") == {"perspective": "p_main"}
    assert result.structured_content == made


async def test_run_kma_model_sends_the_observations_version_and_key(api: FakeApi):
    routes, requests = api
    routes["POST", f"{KMA}/runs"] = ok(receipt(replayed=True))

    result = await call_tool(
        "run_kma_model",
        agent_id="a1",
        perspective="p_main",
        observed={"rate": "high"},
        version=2,
        request_key="k1",
    )

    assert sent(requests, "POST", f"{KMA}/runs") == {
        "perspective": "p_main",
        "observed": {"rate": "high"},
        "version": 2,
        "request_key": "k1",
    }
    assert result.structured_content == receipt(replayed=True)


@pytest.mark.parametrize(
    ("status", "detail"),
    [
        (409, "'nope' is not a variable of this perspective"),
        (409, "this request key was already used for a different run; use a new key"),
        (404, "this KMA has no published version 9"),
        (403, "Not authorized to access this knowledge agent"),
    ],
)
async def test_run_kma_model_errors_reach_the_client(
    api: FakeApi, status: int, detail: str
):
    routes, _ = api
    routes["POST", f"{KMA}/runs"] = httpx2.Response(status, json={"detail": detail})

    result = await call_tool("run_kma_model", agent_id="a1", perspective="p_main")

    assert error_text(result).endswith(f"CrowdSmart API error {status}: {detail}")


async def test_get_kma_run_returns_the_receipt_unchanged(api: FakeApi):
    routes, requests = api
    routes["GET", f"{KMA}/runs/{'f' * 32}"] = ok(receipt())

    result = await call_tool("get_kma_run", agent_id="a1", run_id="f" * 32)

    assert [r.url.path for r in requests] == [f"{KMA}/runs/{'f' * 32}"]
    assert result.structured_content == receipt()


@pytest.mark.parametrize(
    ("tool", "arguments", "path"),
    [
        ("get_kma_history", {}, f"{KMA}/history"),
        ("get_kma_published_version", {"version": 3}, f"{KMA}/history/published/3"),
        (
            "get_kma_build_record",
            {"kind": "build", "record_id": "b1"},
            f"{KMA}/history/builds/b1",
        ),
        (
            "get_kma_build_record",
            {"kind": "refit", "record_id": "r2"},
            f"{KMA}/history/refits/r2",
        ),
        (
            "get_kma_build_record",
            {"kind": "revision", "record_id": "a1"},
            f"{KMA}/history/revisions/a1",
        ),
    ],
)
async def test_history_tools_return_the_record_whole(
    api: FakeApi, tool: str, arguments: dict[str, object], path: str
):
    routes, requests = api
    record = {
        "definition": {"passages": {"d0#0": {"text": "x" * 50_000}}},
        "text_withheld_for": ["d9"],
        "content_sha256": "c" * 64,
    }
    routes["GET", path] = ok(record)

    result = await call_tool(tool, agent_id="a1", **arguments)

    assert [r.url.path for r in requests] == [path]
    assert result.structured_content == record


async def test_get_kma_frozen_forecast_names_the_kma(api: FakeApi):
    routes, requests = api
    path = f"{DOMAINS}/rates/cases/c1/frozen"
    frozen: dict[str, object] = {
        "case_id": "c1",
        "agent": "a1",
        "checks": {"replay": "identical", "inputs_recorded": True},
        "forecast": {"distribution": {"hike": 0.2}, "inputs_snapshot": {"calls": {}}},
    }
    routes["GET", path] = ok(frozen)

    result = await call_tool(
        "get_kma_frozen_forecast", domain_id="rates", case_id="c1", agent_id="a1"
    )

    assert [(r.url.path, dict(r.url.params)) for r in requests] == [
        (path, {"agent": "a1"})
    ]
    assert result.structured_content == frozen
