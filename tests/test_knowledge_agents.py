"""Tests for the Knowledge Agent tools, through an MCP client and a fake API."""

import asyncio
import time
from pathlib import Path

import httpx2
import pytest

from crowdsmart_mcp import knowledge_agents
from tests.helpers import USER_ID, FakeApi, call_tool, error_text, ok, sent

pytestmark = pytest.mark.anyio

AGENTS = "/api/knowledge-agents"
COMMUNITIES = "/api/communities/mine"


def agent(agent_id: str, **fields: object) -> dict[str, object]:
    """A Knowledge Agent as the API returns it (KnowledgeAgentInfo)."""
    return {
        "id": agent_id,
        "user_id": USER_ID,
        "owner_id": USER_ID,
        "name": f"Agent {agent_id}",
        "expertise_headline": "Testing",
        "system_prompt": "A long system prompt the client does not need.",
        "document_count": 2,
        "chunk_count": 10,
        "visibility": "private",
        "generation_mode": "foundation_assisted",
        "allow_foundation_backfill": False,
        "strict_rag": True,
        **fields,
    }


async def test_list_my_communities_returns_ids_and_the_default(api: FakeApi):
    routes, requests = api
    community = {
        "id": "c1",
        "name": "CSLabs Researchers",
        "slug": "cslabs-researchers",
        "description": "Researchers",
        "is_private": False,
        "my_role": "member",
        "is_default": True,
    }
    routes["GET", COMMUNITIES] = ok(
        {"default_community_id": "c1", "communities": [community]}
    )

    result = await call_tool("list_my_communities")

    assert requests[-1].url.params["participant_id"] == USER_ID
    assert result.structured_content == {
        "default_community_id": "c1",
        "communities": [
            {
                "id": "c1",
                "name": "CSLabs Researchers",
                "description": "Researchers",
                "your_role": "member",
            }
        ],
    }


async def test_list_community_members_returns_names_types_and_roles(api: FakeApi):
    routes, requests = api
    member = {
        "participant_id": "p1",
        "name": "Grace Hopper",
        "email": "grace@example.com",
        "type": "human",
        "role": "admin",
        "is_default": False,
        "joined_at": "2026-10-01T12:00:00Z",
    }
    routes["GET", "/api/communities/c1/members"] = ok(
        {"success": True, "members": [member], "count": 1}
    )

    result = await call_tool("list_community_members", community_id="c1")

    assert requests[-1].url.params["participant_id"] == USER_ID
    assert result.structured_content == {
        "members": [
            {
                "id": "p1",
                "name": "Grace Hopper",
                "email": "grace@example.com",
                "type": "human",
                "role": "admin",
                "joined_at": "2026-10-01T12:00:00Z",
            }
        ]
    }


async def test_list_community_members_reports_a_private_community_you_are_not_in(
    api: FakeApi,
):
    routes, _ = api
    routes["GET", "/api/communities/c2/members"] = httpx2.Response(
        403, json={"detail": "Not a member of this community"}
    )

    result = await call_tool("list_community_members", community_id="c2")

    assert "403: Not a member of this community" in error_text(result)


async def test_list_knowledge_agents_separates_own_and_shared(api: FakeApi):
    routes, requests = api
    routes["GET", f"{AGENTS}/user/{USER_ID}"] = ok([agent("a1")])
    routes["GET", f"{AGENTS}/published"] = ok(
        [
            agent("a1", visibility="public"),  # your own agent, also published
            agent(
                "a2",
                user_id="someone",
                owner_id="someone",
                visibility="platform",
                generation_mode="strict_corpus",
            ),
        ]
    )

    result = await call_tool("list_knowledge_agents")

    assert result.structured_content == {
        "yours": [
            {
                "id": "a1",
                "name": "Agent a1",
                "expertise_headline": "Testing",
                "document_count": 2,
                "chunk_count": 10,
                "mode": "generative",
                "visibility": "private",
                "allow_foundation_backfill": False,
            }
        ],
        "shared_with_you": [
            {
                "id": "a2",
                "name": "Agent a2",
                "expertise_headline": "Testing",
                "document_count": 2,
                "chunk_count": 10,
                "mode": "referenced",
                "visibility": "platform",
                "allow_foundation_backfill": False,
            }
        ],
    }
    assert requests[-1].url.params["include_public"] == "true"


async def test_list_knowledge_agents_does_not_call_an_admins_view_yours(
    api: FakeApi,
):
    routes, _ = api
    # For an administrator, the user's list holds every agent on the platform.
    routes["GET", f"{AGENTS}/user/{USER_ID}"] = ok(
        [agent("a1"), agent("a2", user_id="u2", owner_id="u2")]
    )
    routes["GET", f"{AGENTS}/published"] = ok([agent("a1", visibility="public")])

    result = await call_tool("list_knowledge_agents")

    assert result.structured_content is not None
    assert [a["id"] for a in result.structured_content["yours"]] == ["a1"]
    assert [a["id"] for a in result.structured_content["shared_with_you"]] == ["a2"]


async def test_create_knowledge_agent_sends_owner_mode_and_default_community(
    api: FakeApi,
):
    routes, requests = api
    routes["GET", COMMUNITIES] = ok({"default_community_id": "c1", "communities": []})
    created = {"success": True, "agent_id": "a9", "name": "Kanji", "message": "Done"}
    routes["POST", f"{AGENTS}/"] = ok(created)

    result = await call_tool(
        "create_knowledge_agent",
        name="Kanji",
        expertise_headline="Kanji etymology",
        mode="referenced",
    )

    assert sent(requests, "POST", f"{AGENTS}/") == {
        "user_id": USER_ID,
        "name": "Kanji",
        "expertise_headline": "Kanji etymology",
        "system_prompt": None,
        "generation_mode": "strict_corpus",
        "allow_foundation_backfill": False,
        "community_id": "c1",
    }
    assert result.structured_content == created


async def test_update_knowledge_agent_sends_only_the_settings_given(api: FakeApi):
    routes, requests = api
    routes["PATCH", f"{AGENTS}/a1/settings"] = ok({"success": True})

    _ = await call_tool(
        "update_knowledge_agent", agent_id="a1", mode="generative", model="gpt-4o-mini"
    )

    assert sent(requests, "PATCH", f"{AGENTS}/a1/settings") == {
        "generation_mode": "foundation_assisted",
        "model_choice": "gpt-4o-mini",
    }


async def test_set_knowledge_agent_visibility_acts_as_you(api: FakeApi):
    routes, requests = api
    routes["PATCH", f"{AGENTS}/a1/visibility"] = ok({"visibility": "community"})

    _ = await call_tool(
        "set_knowledge_agent_visibility",
        agent_id="a1",
        visibility="community",
        community_id="c1",
    )

    assert requests[-1].url.params["participant_id"] == USER_ID
    assert sent(requests, "PATCH", f"{AGENTS}/a1/visibility") == {
        "visibility": "community",
        "community_id": "c1",
    }


async def test_ask_knowledge_agent_returns_answer_citations_and_confidence(
    api: FakeApi,
):
    routes, requests = api
    routes["POST", f"{AGENTS}/a1/query"] = ok(
        {
            "answer": "A frame groups slots [1]. Frames suit narrow domains.",
            "citations": [
                {
                    "index": 1,
                    "source": "kr.pdf",
                    "excerpt": "kr | Part 1 of 3: A frame groups slots...",
                    "similarity": 0.8,
                    "document_id": "d1",
                    "chunk_id": "c1",
                    "relevance_probability": 0.2,
                }
            ],
            "sources_used": ["kr.pdf"],
            "confidence": 0.8,
            "generation_source": "open_weight_api",
            "knowledge_source": None,
            "evidence": {"mode": "evidence_v4", "parsed": True, "sentences": []},
        }
    )

    result = await call_tool(
        "ask_knowledge_agent", agent_id="a1", question="What is a frame?"
    )

    assert sent(requests, "POST", f"{AGENTS}/a1/query") == {
        "question": "What is a frame?",
        "max_chunks": 5,
    }
    assert result.structured_content == {
        "answer": "A frame groups slots [1]. Frames suit narrow domains.",
        "citations": [
            {
                "index": 1,
                "document": "kr.pdf",
                "document_id": "d1",
                "excerpt": "kr | Part 1 of 3: A frame groups slots...",
            }
        ],
        "confidence": 0.8,
        "generation_source": "open_weight_api",
        "knowledge_source": "documents",
    }


async def test_ask_knowledge_agent_sends_the_api_name_of_a_mode(api: FakeApi):
    routes, requests = api
    routes["POST", f"{AGENTS}/a1/query"] = ok(
        {
            "answer": "Passages...",
            "citations": [],
            "confidence": 0.4,
            "generation_source": "corpus_extractive",
            "knowledge_source": None,
        }
    )

    _ = await call_tool(
        "ask_knowledge_agent",
        agent_id="a1",
        question="q",
        mode="referenced",
        max_chunks=8,
    )

    assert sent(requests, "POST", f"{AGENTS}/a1/query") == {
        "question": "q",
        "max_chunks": 8,
        "query_generation_mode": "strict_corpus",
    }


async def test_list_documents_returns_the_documents(api: FakeApi):
    routes, _ = api
    document = {"id": "d1", "name": "kr.pdf", "processed": True, "chunk_count": 3}
    routes["GET", f"{AGENTS}/a1/documents"] = ok([document])

    result = await call_tool("list_documents", agent_id="a1")

    assert result.structured_content == {"documents": [document]}


async def test_read_document_reports_truncation(api: FakeApi):
    routes, requests = api
    routes["GET", f"{AGENTS}/a1/documents/d1"] = ok(
        {"id": "d1", "name": "kr.pdf", "content": "abcdef"}
    )

    result = await call_tool(
        "read_document", agent_id="a1", document_id="d1", max_chars=5
    )

    assert requests[-1].url.params["max_chars"] == "6"
    assert result.structured_content == {
        "name": "kr.pdf",
        "content": "abcde",
        "truncated": True,
    }


async def test_upload_document_sends_the_file_and_waits_for_extraction(
    api: FakeApi, tmp_path: Path
):
    routes, requests = api
    file = tmp_path / "notes.md"
    _ = file.write_text("# Notes")
    routes["POST", f"{AGENTS}/a1/documents"] = ok(
        {
            "success": True,
            "document_id": "d5",
            "filename": "notes.md",
            "status": "processing",
        }
    )
    done = {
        "document_id": "d5",
        "filename": "notes.md",
        "status": "completed",
        "chunk_count": 2,
    }
    routes["GET", f"{AGENTS}/a1/documents/d5/status"] = ok(done)

    result = await call_tool("upload_document", agent_id="a1", path=str(file))

    upload = next(request for request in requests if request.method == "POST")
    assert upload.headers["content-type"].startswith("multipart/form-data")
    assert b'filename="notes.md"' in upload.content
    assert b"# Notes" in upload.content
    assert result.structured_content == done


async def test_upload_document_returns_while_extraction_continues(
    api: FakeApi, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    routes, _ = api
    # The status is read once, then the wait ends during the sleep.
    monkeypatch.setattr(knowledge_agents, "UPLOAD_WAIT_SECONDS", 0.5)
    monkeypatch.setattr(knowledge_agents, "UPLOAD_POLL_SECONDS", 10)
    file = tmp_path / "scan.pdf"
    _ = file.write_bytes(b"%PDF-1.4")
    routes["POST", f"{AGENTS}/a1/documents"] = ok(
        {"document_id": "d6", "status": "processing"}
    )
    processing = {"document_id": "d6", "filename": "scan.pdf", "status": "processing"}
    routes["GET", f"{AGENTS}/a1/documents/d6/status"] = ok(processing)

    result = await call_tool("upload_document", agent_id="a1", path=str(file))

    assert result.structured_content == processing


async def test_upload_document_keeps_the_document_id_when_status_fails(
    api: FakeApi, tmp_path: Path
):
    routes, requests = api
    file = tmp_path / "notes.md"
    _ = file.write_text("# Notes")
    routes["POST", f"{AGENTS}/a1/documents"] = ok(
        {"document_id": "d7", "status": "processing"}
    )
    routes["GET", f"{AGENTS}/a1/documents/d7/status"] = httpx2.Response(
        503, json={"detail": "Status service unavailable"}
    )

    result = await call_tool("upload_document", agent_id="a1", path=str(file))

    assert "Uploaded as document d7" in error_text(result)
    assert "before you upload it again" in error_text(result)
    assert [r.method for r in requests if r.url.path.endswith("/documents")] == ["POST"]


async def test_upload_document_stops_waiting_at_its_deadline(
    api: FakeApi, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    routes, _ = api
    monkeypatch.setattr(knowledge_agents, "UPLOAD_WAIT_SECONDS", 0.05)
    file = tmp_path / "slow.pdf"
    _ = file.write_bytes(b"%PDF-1.4")
    receipt = {"document_id": "d8", "status": "processing"}
    routes["POST", f"{AGENTS}/a1/documents"] = ok(receipt)

    async def slow_status(*_: object) -> dict[str, object]:
        await asyncio.sleep(10)
        raise AssertionError("not reached")

    monkeypatch.setattr(knowledge_agents, "get_document_status", slow_status)

    started = time.monotonic()
    result = await call_tool("upload_document", agent_id="a1", path=str(file))

    assert time.monotonic() - started < 2
    assert result.structured_content == receipt


async def test_get_document_status_reads_the_upload_status(api: FakeApi):
    routes, _ = api
    failed = {"document_id": "d9", "status": "failed", "error": "Unreadable PDF"}
    routes["GET", f"{AGENTS}/a1/documents/d9/status"] = ok(failed)

    result = await call_tool("get_document_status", agent_id="a1", document_id="d9")

    assert result.structured_content == failed


@pytest.mark.parametrize("name", ["missing.pdf", "a-folder"])
async def test_upload_document_reports_a_file_it_cannot_read(
    api: FakeApi, tmp_path: Path, name: str
):
    _, requests = api
    (tmp_path / "a-folder").mkdir()

    result = await call_tool(
        "upload_document", agent_id="a1", path=str(tmp_path / name)
    )

    assert f"Cannot read {tmp_path / name}" in error_text(result)
    assert requests == []


async def test_add_text_document_sends_text_and_source(api: FakeApi):
    routes, requests = api
    created = {"success": True, "document_id": "d9", "title": "Note", "chunk_count": 1}
    routes["POST", f"{AGENTS}/a1/text"] = ok(created)

    result = await call_tool(
        "add_text_document",
        agent_id="a1",
        title="Note",
        text="Body",
        source_url="https://example.com/note",
    )

    assert sent(requests, "POST", f"{AGENTS}/a1/text") == {
        "title": "Note",
        "text": "Body",
        "source_url": "https://example.com/note",
        "author": None,
        "timestamp": None,
        "source_type": None,
    }
    assert result.structured_content == created


async def test_delete_document_deletes_it(api: FakeApi):
    routes, requests = api
    routes["DELETE", f"{AGENTS}/a1/documents/d1"] = ok({"success": True})

    result = await call_tool("delete_document", agent_id="a1", document_id="d1")

    assert (requests[-1].method, requests[-1].url.path) == (
        "DELETE",
        f"{AGENTS}/a1/documents/d1",
    )
    assert result.structured_content == {"success": True}


async def test_check_corpus_quality_returns_only_flagged_documents(api: FakeApi):
    routes, _ = api
    healthy: dict[str, object] = {
        "document_id": "d1",
        "severity": "healthy",
        "issues": [],
    }
    damaged = {
        "document_id": "d2",
        "document_name": "scan.pdf",
        "severity": "damaged",
        "issues": [{"code": "garbled", "label": "Garbled text (OCR errors)"}],
        "recommended_action": "Delete this document, then upload the original file again",
    }
    summary = {"damaged": 1, "check": 0, "healthy": 1}
    unrecorded = {
        "document_id": "d3",
        "source": "notes.pdf",
        "passages": 4,
        "parts_expected": 9,
        "complete": False,
    }
    routes["GET", f"{AGENTS}/a1/corpus-quality"] = ok(
        {
            "agent_id": "a1",
            "summary": summary,
            "documents": [healthy, damaged],
            "unrecorded_uploads": [unrecorded],
        }
    )

    result = await call_tool("check_corpus_quality", agent_id="a1")

    assert result.structured_content == {
        "summary": summary,
        "flagged": [damaged],
        "unrecorded_uploads": [unrecorded],
    }


async def test_tools_refuse_a_missing_route_cleanly(api: FakeApi):
    routes, _ = api
    routes["GET", f"{AGENTS}/a1/documents"] = httpx2.Response(
        404, json={"detail": "Knowledge Agent not found"}
    )

    result = await call_tool("list_documents", agent_id="a1")

    assert error_text(result).endswith(
        "CrowdSmart API error 404: Knowledge Agent not found"
    )
