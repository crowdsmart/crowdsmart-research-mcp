"""Tests for the server as a whole: its curated tools, their safety hints, errors and startup."""

import httpx2
import pytest
from mcp import Client

from crowdsmart_mcp import server
from tests.helpers import FakeApi, call_tool, error_text

pytestmark = pytest.mark.anyio

KNOWLEDGE_AGENT_TOOLS = {
    "list_my_communities",
    "list_community_members",
    "list_knowledge_agents",
    "create_knowledge_agent",
    "update_knowledge_agent",
    "set_knowledge_agent_visibility",
    "ask_knowledge_agent",
    "list_documents",
    "read_document",
    "upload_document",
    "get_document_status",
    "add_text_document",
    "delete_document",
    "check_corpus_quality",
}
JAM_TOOLS = {
    "list_jams",
    "get_jam",
    "create_jam",
    "launch_jam",
    "add_agents_to_jam",
    "get_jam_results",
    "get_jam_responses",
}
KMA_TOOLS = {
    "list_kma_domains",
    "get_kma_domain",
    "create_kma_domain",
    "add_kma_case",
    "set_kma_case_profile",
    "resolve_kma_case",
    "mark_kma_case_unscored",
    "get_kma_scoreboard",
    "list_kmas",
    "create_kma",
    "enable_kma",
    "attach_kma_to_domain",
    "list_kma_documents",
    "read_kma_extraction",
    "review_kma_document",
    "tag_kma_document",
    "check_kma_build_preflight",
    "start_kma_build",
    "get_kma_builds",
    "decide_kma_build",
    "get_kma_forecast",
    "get_kma_model",
    "freeze_kma_forecast",
    "get_kma_switches",
    "set_kma_switch",
    "list_kma_needs",
    "ask_kma_need",
    "get_kma_cohort",
    "invite_to_kma_cohort",
    "remove_from_kma_cohort",
}

READ_ONLY = {
    "list_my_communities",
    "list_community_members",
    "list_knowledge_agents",
    "list_documents",
    "read_document",
    "get_document_status",
    "check_corpus_quality",
    "list_jams",
    "get_jam",
    "get_jam_results",
    "get_jam_responses",
    "list_kma_domains",
    "get_kma_domain",
    "get_kma_scoreboard",
    "list_kmas",
    "list_kma_documents",
    "read_kma_extraction",
    "check_kma_build_preflight",
    "get_kma_model",
    "get_kma_switches",
    "get_kma_cohort",
}
DESTRUCTIVE = {
    "update_knowledge_agent",
    "set_knowledge_agent_visibility",
    "delete_document",
    "set_kma_case_profile",
    "review_kma_document",
    "enable_kma",
    "tag_kma_document",
    "decide_kma_build",
    "set_kma_switch",
    "remove_from_kma_cohort",
}
# Not read-only, because they can queue model calls on CrowdSmart's worker.
QUEUE_ONLY = {"get_kma_builds", "get_kma_forecast", "list_kma_needs"}


async def test_server_offers_only_the_curated_tools():
    async with Client(server.mcp) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert set(tools) == KNOWLEDGE_AGENT_TOOLS | JAM_TOOLS | KMA_TOOLS
    hints = {
        name: tool.annotations
        for name, tool in tools.items()
        if tool.annotations is not None
    }
    assert set(hints) == set(tools)
    assert {name for name, hint in hints.items() if hint.read_only_hint} == READ_ONLY
    destructive = {name for name, hint in hints.items() if hint.destructive_hint}
    assert destructive == DESTRUCTIVE
    idempotent = {name for name, hint in hints.items() if hint.idempotent_hint}
    assert idempotent == QUEUE_ONLY


async def test_every_request_sends_the_api_key(api: FakeApi):
    routes, requests = api
    routes["GET", "/api/collaborations/active"] = httpx2.Response(
        200, json={"collaborations": []}
    )

    _ = await call_tool("list_jams")

    assert {request.headers["Authorization"] for request in requests} == {
        "Bearer crc_test"
    }


async def test_api_errors_reach_the_client(api: FakeApi):
    routes, _ = api
    routes["GET", "/api/knowledge-agents/a1/documents"] = httpx2.Response(
        403, json={"detail": "Not authorized to access this knowledge agent"}
    )

    result = await call_tool("list_documents", agent_id="a1")

    assert error_text(result).endswith(
        "CrowdSmart API error 403: Not authorized to access this knowledge agent"
    )


async def test_validation_errors_name_the_field(api: FakeApi):
    routes, _ = api
    routes["POST", "/api/knowledge-agents/a1/text"] = httpx2.Response(
        422,
        json={
            "detail": [
                {"loc": ["body", "title"], "msg": "Field required"},
                {"loc": ["body", "text"], "msg": "Input should be a string"},
            ]
        },
    )

    result = await call_tool("add_text_document", agent_id="a1", title="t", text="x")

    assert error_text(result).endswith(
        "CrowdSmart API error 422: body.title: Field required; body.text: Input should be a string"
    )


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        (
            httpx2.Response(200, text="<html>login</html>"),
            "not JSON: <html>login</html>",
        ),
        (
            httpx2.Response(307, headers={"location": "/elsewhere"}),
            "CrowdSmart API error 307",
        ),
        (httpx2.Response(422, json={"detail": ["bad input"]}), "bad input"),
    ],
)
async def test_unexpected_responses_are_reported(
    api: FakeApi, reply: httpx2.Response, message: str
):
    routes, requests = api
    routes["GET", "/api/knowledge-agents/a1/documents"] = reply

    result = await call_tool("list_documents", agent_id="a1")

    assert message in error_text(result)
    assert len(requests) == 1  # a redirect is not followed


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        (
            "ask_knowledge_agent",
            {"agent_id": "../human-auth/api-key#", "question": "q"},
        ),
        (
            "delete_document",
            {"agent_id": "a1", "document_id": "../../a1?force_delete=true"},
        ),
        ("delete_document", {"agent_id": "a1?force_delete=true#", "document_id": "d1"}),
        ("list_documents", {"agent_id": "a1%2F..%2F"}),
        ("launch_jam", {"jam_id": "j1/../../human-auth/api-key"}),
        ("read_document", {"agent_id": "a1", "document_id": "d1", "max_chars": -1}),
        ("get_kma_domain", {"domain_id": "d1/../../human-auth/api-key"}),
        ("get_kma_forecast", {"agent_id": "a1", "case_id": "c1?agent=x#"}),
        (
            "decide_kma_build",
            {"agent_id": "a1", "build_id": "b1/../../b2", "action": "publish"},
        ),
        (
            "freeze_kma_forecast",
            {"domain_id": "d.1", "case_id": "c1", "agent_id": "a1"},
        ),
    ],
)
async def test_invalid_arguments_send_no_request(
    api: FakeApi, tool: str, arguments: dict[str, object]
):
    _, requests = api

    result = await call_tool(tool, **arguments)

    assert result.is_error
    assert requests == []


async def test_unreachable_api_is_reported(api: FakeApi):
    routes, _ = api
    routes["GET", "/api/knowledge-agents/a1/documents"] = httpx2.ConnectError(
        "Connection refused"
    )

    result = await call_tool("list_documents", agent_id="a1")

    assert "Could not reach CrowdSmart" in error_text(result)


def test_main_exits_without_an_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CROWDSMART_API_KEY", raising=False)

    with pytest.raises(SystemExit) as exit_info:
        server.main()

    assert "CROWDSMART_API_KEY" in str(exit_info.value.code)
