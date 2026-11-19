"""Tests for the tools that correct one fact of a KMA, through an MCP client and a fake API."""

import httpx2
import pytest

from tests.helpers import FakeApi, call_tool, error_text, ok, sent

pytestmark = pytest.mark.anyio

KMA = "/api/knowledge-agents/a1/kma/v2"
CASE = "/api/kma/v2/domains/rates/cases/c1"
REPORT = {"written": False, "before": {"average": {"hike": 0.4}}, "after": {}}


@pytest.mark.parametrize(
    ("tool", "arguments", "path", "body"),
    [
        (
            "correct_kma_case_outcome",
            {
                "domain_id": "rates",
                "case_id": "c1",
                "state": "hold",
                "source": "https://example.org/decision",
                "date": "2026-10-28",
                "reason": "the press release was misread",
                "replaces": 7,
            },
            f"{CASE}/resolution/correct",
            {
                "state": "hold",
                "source": "https://example.org/decision",
                "date": "2026-10-28",
                "reason": "the press release was misread",
                "replaces": 7,
                "preview": True,
            },
        ),
        (
            "retract_kma_case_outcome",
            {
                "domain_id": "rates",
                "case_id": "c1",
                "reason": "recorded on the wrong case",
                "replaces": 7,
            },
            f"{CASE}/resolution/retract",
            {"reason": "recorded on the wrong case", "replaces": 7, "preview": True},
        ),
        (
            "set_aside_kma_reading",
            {"agent_id": "a1", "case_id": "c1", "call": "k9", "reason": "misread"},
            f"{KMA}/cases/c1/readings/set-aside",
            {"call": "k9", "reason": "misread", "preview": True},
        ),
        (
            "give_kma_reading",
            {
                "agent_id": "a1",
                "case_id": "c1",
                "passage": "d1#0",
                "variable": "inflation",
                "state": "rising",
                "quote": "prices rose 4%",
                "reason": "the model missed the table",
            },
            f"{KMA}/cases/c1/readings/state",
            {
                "passage": "d1#0",
                "variable": "inflation",
                "state": "rising",
                "quote": "prices rose 4%",
                "reason": "the model missed the table",
                "preview": True,
            },
        ),
        (
            "give_kma_reading",
            {
                "agent_id": "a1",
                "case_id": "c1",
                "passage": "d1#0",
                "variable": "inflation",
                "state": "not_stated",
                "reason": "it does not say",
            },
            f"{KMA}/cases/c1/readings/state",
            {
                "passage": "d1#0",
                "variable": "inflation",
                "state": "not_stated",
                "reason": "it does not say",
                "preview": True,
            },
        ),
        (
            "restore_kma_reading",
            {"agent_id": "a1", "case_id": "c1", "reason": "it was right", "call": "k9"},
            f"{KMA}/cases/c1/readings/restore",
            {"reason": "it was right", "call": "k9", "preview": True},
        ),
        (
            "restore_kma_reading",
            {
                "agent_id": "a1",
                "case_id": "c1",
                "reason": "take mine back",
                "passage": "d1#0",
                "variable": "inflation",
            },
            f"{KMA}/cases/c1/readings/restore",
            {
                "reason": "take mine back",
                "passage": "d1#0",
                "variable": "inflation",
                "preview": True,
            },
        ),
        (
            "retry_kma_failed_call",
            {"agent_id": "a1", "case_id": "c1", "call": "k3", "reason": "a timeout"},
            f"{KMA}/cases/c1/readings/retry",
            {"call": "k3", "reason": "a timeout", "preview": True},
        ),
    ],
)
async def test_corrections_preview_unless_told_otherwise(
    api: FakeApi,
    tool: str,
    arguments: dict[str, object],
    path: str,
    body: dict[str, object],
):
    routes, requests = api
    routes["POST", path] = ok(REPORT)

    result = await call_tool(tool, **arguments)

    assert sent(requests, "POST", path) == body
    assert result.structured_content == REPORT

    requests.clear()
    _ = await call_tool(tool, **arguments, preview=False)

    assert sent(requests, "POST", path) == {**body, "preview": False}


async def test_a_stale_correction_is_refused_with_the_reason(api: FakeApi):
    routes, requests = api
    refusal = (
        "the resolution in force is not the one named (it was corrected in the "
        + "meantime); read the case again"
    )
    routes["POST", f"{CASE}/resolution/retract"] = httpx2.Response(
        409, json={"detail": refusal}
    )

    result = await call_tool(
        "retract_kma_case_outcome",
        domain_id="rates",
        case_id="c1",
        reason="wrong case",
        replaces=3,
        preview=False,
    )

    assert error_text(result).endswith(f"CrowdSmart API error 409: {refusal}")
    assert len(requests) == 1  # no second try


@pytest.mark.parametrize(
    ("tool", "arguments", "method", "path", "body"),
    [
        (
            "state_kma_row",
            {
                "agent_id": "a1",
                "perspective": "p_main",
                "variable": "inflation",
                "probabilities": {"rising": 0.7},
                "reason": "the bank's own projection",
            },
            "POST",
            f"{KMA}/rows/state",
            {
                "perspective": "p_main",
                "variable": "inflation",
                "probabilities": {"rising": 0.7},
                "reason": "the bank's own projection",
            },
        ),
        (
            "state_kma_row",
            {
                "agent_id": "a1",
                "perspective": "p_main",
                "variable": "decision",
                "given": {"inflation": "rising"},
                "probabilities": {"hike": 0.6, "hold": 0.3, "cut": 0.1},
                "reason": "r",
            },
            "POST",
            f"{KMA}/rows/state",
            {
                "perspective": "p_main",
                "variable": "decision",
                "given": {"inflation": "rising"},
                "probabilities": {"hike": 0.6, "hold": 0.3, "cut": 0.1},
                "reason": "r",
            },
        ),
        (
            "withdraw_kma_answer",
            {"agent_id": "a1", "reason": "answered in error", "question": "q4"},
            "POST",
            f"{KMA}/answers/withdraw",
            {"reason": "answered in error", "question": "q4"},
        ),
        (
            "withdraw_kma_answer",
            {"agent_id": "a1", "reason": "a new source", "statement": 41},
            "POST",
            f"{KMA}/answers/withdraw",
            {"reason": "a new source", "statement": 41},
        ),
        (
            "start_kma_revision",
            {"agent_id": "a1", "perspective": "p_main"},
            "POST",
            f"{KMA}/revise",
            {"perspective": "p_main"},
        ),
        (
            "publish_kma_revision",
            {"agent_id": "a1", "revision_id": "a2", "model_sha256": "m" * 64},
            "POST",
            f"{KMA}/revise/a2/publish",
            {"model_sha256": "m" * 64},
        ),
        (
            "start_kma_source_repair",
            {
                "agent_id": "a1",
                "documents": ["d0"],
                "reason": "the report was retracted",
                "show_text": False,
            },
            "POST",
            f"{KMA}/sources/repair",
            {
                "documents": ["d0"],
                "reason": "the report was retracted",
                "show_text": False,
            },
        ),
        (
            "publish_kma_source_repair",
            {
                "agent_id": "a1",
                "repair_id": "s1",
                "perspective": "p_main",
                "model_sha256": "m" * 64,
            },
            "POST",
            f"{KMA}/sources/repair/s1/publish",
            {"perspective": "p_main", "model_sha256": "m" * 64},
        ),
        (
            "get_kma_stale_outcomes",
            {"agent_id": "a1"},
            "GET",
            f"{KMA}/outcomes/stale",
            None,
        ),
        (
            "get_kma_reading_corrections",
            {"agent_id": "a1"},
            "GET",
            f"{KMA}/readings",
            None,
        ),
        (
            "get_kma_stale_sources",
            {"agent_id": "a1"},
            "GET",
            f"{KMA}/sources/stale",
            None,
        ),
        (
            "get_kma_source_repair",
            {"agent_id": "a1"},
            "GET",
            f"{KMA}/sources/repair",
            None,
        ),
        (
            "get_kma_source_repair",
            {"agent_id": "a1", "repair_id": "s1"},
            "GET",
            f"{KMA}/sources/repair/s1",
            None,
        ),
    ],
)
async def test_correction_tools_call_their_route(
    api: FakeApi,
    tool: str,
    arguments: dict[str, object],
    method: str,
    path: str,
    body: dict[str, object] | None,
):
    routes, requests = api
    reply = {"report": [{"x": 1}], "next": "start a revision of p_main"}
    routes[method, path] = ok(reply)

    result = await call_tool(tool, **arguments)

    assert [(r.method, r.url.path) for r in requests] == [(method, path)]
    if body is not None:
        assert sent(requests, method, path) == body
    assert result.structured_content == reply


async def test_publish_kma_refit_sends_no_body(api: FakeApi):
    routes, requests = api
    published = {"refit": "r2", "stage": "published", "model": {"sha256": "m" * 64}}
    routes["POST", f"{KMA}/refit/r2/publish"] = ok(published)

    result = await call_tool("publish_kma_refit", agent_id="a1", refit_id="r2")

    assert [(r.method, r.url.path, r.content) for r in requests] == [
        ("POST", f"{KMA}/refit/r2/publish", b"")
    ]
    assert result.structured_content == published


@pytest.mark.parametrize(
    ("tool", "arguments", "path", "detail"),
    [
        (
            "publish_kma_revision",
            {"agent_id": "a1", "revision_id": "a2", "model_sha256": "0" * 64},
            f"{KMA}/revise/a2/publish",
            "the candidate model has changed since it was previewed; read the "
            + "revision again",
        ),
        (
            "publish_kma_source_repair",
            {
                "agent_id": "a1",
                "repair_id": "s1",
                "perspective": "p_main",
                "model_sha256": "0" * 64,
            },
            f"{KMA}/sources/repair/s1/publish",
            "the candidate model has changed since it was previewed; read the "
            + "repair again",
        ),
    ],
)
async def test_a_publish_with_another_hash_is_refused_once(
    api: FakeApi, tool: str, arguments: dict[str, object], path: str, detail: str
):
    routes, requests = api
    routes["POST", path] = httpx2.Response(409, json={"detail": detail})

    result = await call_tool(tool, **arguments)

    assert error_text(result).endswith(f"CrowdSmart API error 409: {detail}")
    assert [(r.method, r.url.path) for r in requests] == [("POST", path)]


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("publish_kma_revision", {"agent_id": "a1", "revision_id": "a2"}),
        (
            "publish_kma_source_repair",
            {"agent_id": "a1", "repair_id": "s1", "perspective": "p_main"},
        ),
        (
            "start_kma_source_repair",
            {"agent_id": "a1", "documents": ["d0"], "reason": "retracted"},
        ),
    ],
)
async def test_a_publication_or_repair_needs_its_explicit_choice(
    api: FakeApi, tool: str, arguments: dict[str, object]
):
    _, requests = api

    result = await call_tool(tool, **arguments)

    assert result.is_error
    assert requests == []
