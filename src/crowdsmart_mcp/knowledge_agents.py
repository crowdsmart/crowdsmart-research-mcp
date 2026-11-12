"""Knowledge Agent (KA) tools: create and share agents, ask them questions, manage their documents.

A Knowledge Agent answers questions from its own documents and cites them. Community
tools are here too, because a community is where an agent is created and shared.
"""

import asyncio
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from crowdsmart_mcp import api
from crowdsmart_mcp.api import ADDS, CHANGES, READS, Id
from crowdsmart_mcp.app import mcp

AGENTS = "/api/knowledge-agents"

# The API's names for the two knowledge modes, by their product names.
MODES = {"generative": "foundation_assisted", "referenced": "strict_corpus"}
Mode = Literal["generative", "referenced"]

# How long upload_document waits for text extraction: under the 60-second request
# timeout that many MCP clients use, so that the client still gets the document_id.
UPLOAD_WAIT_SECONDS = 45
UPLOAD_POLL_SECONDS = 3


@mcp.tool(annotations=READS)
async def list_my_communities() -> dict[str, Any]:
    """List the communities you belong to, and your default community.

    A community ID places a new agent or Jam in that community, or shares a
    Knowledge Agent with its members.
    """
    user = await api.me()
    result = await api.my_communities(user["user_id"])
    return {
        "default_community_id": result["default_community_id"],
        "communities": [
            {
                "id": community["id"],
                "name": community["name"],
                "description": community.get("description"),
                "your_role": community.get("my_role"),
            }
            for community in result["communities"]
        ],
    }


@mcp.tool(annotations=READS)
async def list_community_members(community_id: Id) -> dict[str, Any]:
    """List the members of a community, with their roles and email addresses.

    You can list a public community, or a private one that you belong to.
    "type" is "human" for a person or "ai_agent" for an agent. Knowledge Agents
    shared with a community are not members: see list_knowledge_agents. "role"
    is "admin" or "member". To invite members to a Jam, give their emails to
    create_jam as invite_emails.

    Args:
        community_id: Community ID, from list_my_communities.
    """
    user = await api.me()
    result = await api.call(
        "GET",
        f"/api/communities/{community_id}/members",
        params={"participant_id": user["user_id"]},
    )
    return {
        "members": [
            {
                "id": member["participant_id"],
                "name": member.get("name"),
                "email": member.get("email"),
                "type": member.get("type"),
                "role": member["role"],
                "joined_at": member.get("joined_at"),
            }
            for member in result["members"]
        ]
    }


def _agent_summary(agent: dict[str, Any]) -> dict[str, Any]:
    # The API treats every mode except foundation_assisted as Referenced Retrieval.
    generative = agent["generation_mode"] == MODES["generative"]
    return {
        "id": agent["id"],
        "name": agent["name"],
        "expertise_headline": agent["expertise_headline"],
        "document_count": agent["document_count"],
        "chunk_count": agent["chunk_count"],
        "mode": "generative" if generative else "referenced",
        "model": agent.get("model_choice"),
        "visibility": agent.get("visibility"),
        "allow_foundation_backfill": agent["allow_foundation_backfill"],
    }


@mcp.tool(annotations=READS)
async def list_knowledge_agents() -> dict[str, Any]:
    """List the Knowledge Agents you can ask: your own, and those of other people.

    A Knowledge Agent answers from its own corpus of documents. Other people's
    agents are those published to one of your communities, to the whole platform
    or to the public (and, for an administrator, every agent).
    "mode" is the agent's default way of answering (see ask_knowledge_agent), and
    "model" the language model for its generative answers. "chunk_count" is the
    number of stored passages.
    "allow_foundation_backfill" means the agent can also answer from the model's
    general knowledge. Such answers are labeled.
    """
    user_id = (await api.me())["user_id"]
    listed = await api.call("GET", f"{AGENTS}/user/{user_id}")
    published = await api.call(
        "GET", f"{AGENTS}/published", params={"include_public": True}
    )
    listed_ids = {agent["id"] for agent in listed}
    agents = listed + [agent for agent in published if agent["id"] not in listed_ids]
    # For an administrator the user's list holds every agent, so check the owner.
    return {
        "yours": [_agent_summary(a) for a in agents if a["user_id"] == user_id],
        "shared_with_you": [
            _agent_summary(a) for a in agents if a["user_id"] != user_id
        ],
    }


@mcp.tool(annotations=ADDS)
async def create_knowledge_agent(
    name: str,
    expertise_headline: str,
    system_prompt: str | None = None,
    mode: Mode = "generative",
    allow_foundation_backfill: bool = False,
    community_id: str | None = None,
) -> dict[str, Any]:
    """Create a Knowledge Agent that you own. It is private and has no documents yet.

    Add documents with upload_document or add_text_document. To let others ask the
    agent, share it with set_knowledge_agent_visibility. To have several agents
    discuss a topic, give each one its own perspective (expertise_headline and
    system_prompt) and its own documents, then put them in a Jam with create_jam.
    Your agents do not need to be shared to take part in your Jam.

    Args:
        name: The agent's name.
        expertise_headline: One line on what the agent knows, shown on its card.
        system_prompt: How the agent describes itself and its focus. It does not
            need to tell the agent to keep to its documents: it does that already.
        mode: Default way of answering. "generative" writes answers that cite
            passages. "referenced" returns the passages word for word.
        allow_foundation_backfill: Let the agent answer from the model's general
            knowledge when its documents cannot. Such answers are labeled.
        community_id: Home community, from list_my_communities. Default: your
            default community.
    """
    user = await api.me()
    body = {
        "user_id": user["user_id"],
        "name": name,
        "expertise_headline": expertise_headline,
        "system_prompt": system_prompt,
        "generation_mode": MODES[mode],
        "allow_foundation_backfill": allow_foundation_backfill,
        "community_id": community_id or await api.default_community(user["user_id"]),
    }
    return await api.call("POST", f"{AGENTS}/", json=body)


@mcp.tool(annotations=CHANGES)
async def update_knowledge_agent(
    agent_id: Id,
    name: str | None = None,
    expertise_headline: str | None = None,
    system_prompt: str | None = None,
    mode: Mode | None = None,
    model: Literal["open_weight", "gpt-4o-mini"] | None = None,
) -> dict[str, Any]:
    """Change the settings of a Knowledge Agent you own. Settings you leave out keep their values.

    Args:
        agent_id: ID of a Knowledge Agent you own.
        name: New name.
        expertise_headline: New one-line description.
        system_prompt: New system prompt. It replaces the current one.
        mode: New default way of answering: "generative" or "referenced".
        model: Language model for generative answers.
    """
    settings = {
        "name": name,
        "expertise_headline": expertise_headline,
        "system_prompt": system_prompt,
        "generation_mode": MODES[mode] if mode is not None else None,
        "model_choice": model,
    }
    changes = {key: value for key, value in settings.items() if value is not None}
    return await api.call("PATCH", f"{AGENTS}/{agent_id}/settings", json=changes)


@mcp.tool(annotations=CHANGES)
async def set_knowledge_agent_visibility(
    agent_id: Id,
    visibility: Literal["private", "community", "platform", "public"],
    community_id: str | None = None,
) -> dict[str, Any]:
    """Choose who can ask a Knowledge Agent you own.

    "private": you and platform administrators. "community": the members of one
    community (give community_id). "platform": anyone signed in who belongs to a
    community. "public": anyone with the agent's link, without signing in.

    Args:
        agent_id: ID of a Knowledge Agent you own.
        visibility: "private", "community", "platform" or "public".
        community_id: The community, for "community", from list_my_communities.
    """
    user = await api.me()
    return await api.call(
        "PATCH",
        f"{AGENTS}/{agent_id}/visibility",
        params={"participant_id": user["user_id"]},
        json={"visibility": visibility, "community_id": community_id},
    )


@mcp.tool(annotations=ADDS)
async def ask_knowledge_agent(
    agent_id: Id,
    question: str,
    mode: Mode | None = None,
    max_chunks: int = 5,
    verbose: bool = False,
) -> dict[str, Any]:
    """Ask a Knowledge Agent a question and get an answer from its documents, with citations.

    Generative mode writes an answer. A sentence ending in a citation such as [1]
    is evidence: it was checked against passage 1, or is shown in the passage's
    exact words. A sentence without a citation is the agent's own reasoning, and
    is not checked against the passages.
    Referenced mode returns the cited passages word for word, with no model writing.
    When the documents do not cover the question, the agent says so.

    "confidence" is CrowdSmart's retrieval score, from 0 to 1: how well the best
    passages match the question. It does not show whether the answer is right.
    "generation_source" says how the answer was produced (for example
    "corpus_extractive" or "abstained"). "knowledge_source" is "documents" unless
    general-knowledge backfill contributed. Each question is asked on its own,
    without earlier questions as context. CrowdSmart records each question in
    the agent's query history.

    verbose adds the details needed to check or repeat an answer:
    - "evidence": each written sentence, as "evidence" (with its passage number,
      quote, chunk_id and check "status": "verified", "quote_used" when the exact
      quote replaced the sentence, or "quote_not_found" when it was removed) or
      as "reasoning"; with "counts" per kind and the number "removed". Present
      only for answers written as typed sentences.
    - "passages": the number of passages "requested" (max_chunks) and
      "returned" with the answer. When the agent declines before writing, the
      returned passages are the closest ones; they were not used to write.
    - each citation's chunk_id, "similarity" and "relevance_probability".
    - "decision_trace" (why the agent answered, declined or fell back),
      "effective_config" (the settings applied, when CrowdSmart reports them)
      and "interaction_id" (the recorded question). Each is null if absent.

    Args:
        agent_id: Knowledge Agent ID, from list_knowledge_agents.
        question: The question to answer from the agent's documents.
        mode: "generative" or "referenced". Omit to use the agent's own setting.
        max_chunks: Number of passages to retrieve (default 5).
        verbose: Add the evidence record, passage counts and settings (default
            false). The response is longer.
    """
    body: dict[str, Any] = {"question": question, "max_chunks": max_chunks}
    if mode is not None:
        body["query_generation_mode"] = MODES[mode]
    result = await api.call("POST", f"{AGENTS}/{agent_id}/query", json=body)
    answer = {
        "answer": result["answer"],
        "citations": api.citations(result["citations"], verbose=verbose),
        "confidence": result.get("confidence"),
        "generation_source": result["generation_source"],
        "knowledge_source": result.get("knowledge_source") or "documents",
    }
    if verbose:
        answer["evidence"] = result.get("evidence")
        answer["passages"] = {
            "requested": max_chunks,
            "returned": len(result["citations"] or []),
        }
        answer["decision_trace"] = result.get("decision_trace")
        answer["effective_config"] = result.get("effective_config")
        answer["interaction_id"] = result.get("interaction_id")
    return answer


@mcp.tool(annotations=READS)
async def list_documents(agent_id: Id) -> dict[str, Any]:
    """List the documents in a Knowledge Agent's corpus.

    Args:
        agent_id: Knowledge Agent ID, from list_knowledge_agents.
    """
    return {"documents": await api.call("GET", f"{AGENTS}/{agent_id}/documents")}


@mcp.tool(annotations=READS)
async def read_document(
    agent_id: Id,
    document_id: Id,
    max_chars: Annotated[int, Field(ge=1)] = 20_000,
) -> dict[str, Any]:
    """Read the text of a document in a Knowledge Agent's corpus, for example to check a citation.

    The text is rebuilt from the stored passages: each passage starts with a
    "title | Part n of m:" header, and neighboring passages can overlap.

    Args:
        agent_id: Knowledge Agent ID.
        document_id: Document ID, from list_documents or an answer's citations.
        max_chars: Maximum number of characters to return (default 20,000).
    """
    # One extra character shows whether the text was cut.
    document = await api.call(
        "GET",
        f"{AGENTS}/{agent_id}/documents/{document_id}",
        params={"max_chars": max_chars + 1},
    )
    content = document["content"]
    return {
        "name": document["name"],
        "content": content[:max_chars],
        "truncated": len(content) > max_chars,
    }


@mcp.tool(annotations=ADDS)
async def upload_document(agent_id: Id, path: str) -> dict[str, Any]:
    """Upload a file from this computer to a Knowledge Agent you own, and wait for its text.

    Formats: PDF, DOCX, TXT, MD, JSON, CSV, TSV and XLSX. This waits up to 45
    seconds while CrowdSmart extracts the text, and returns the status:
    "completed" (with the number of passages), "failed" (with the error) or
    "processing" (check later with get_document_status). Upload only files the
    user chose.

    Args:
        agent_id: ID of a Knowledge Agent you own.
        path: Path of the file on the computer that runs this server.
    """
    file = Path(path).expanduser()
    try:
        content = file.read_bytes()
    except OSError as error:  # the SDK hides an unexpected error's message
        raise ToolError(f"Cannot read {file}: {error.strerror}") from error
    upload = await api.call(
        "POST", f"{AGENTS}/{agent_id}/documents", files={"file": (file.name, content)}
    )
    document_id = upload["document_id"]
    status = upload
    try:
        async with asyncio.timeout(UPLOAD_WAIT_SECONDS):
            while True:
                status = await get_document_status(agent_id, document_id)
                if status["status"] in ("completed", "failed"):
                    break
                await asyncio.sleep(UPLOAD_POLL_SECONDS)
    except TimeoutError:
        pass  # still processing: return the last status, with its document_id
    except ToolError as error:
        raise ToolError(
            f"Uploaded as document {document_id}, but its status could not be read "
            + f"({error}). Check it with get_document_status before you upload it again."
        ) from error
    return status


@mcp.tool(annotations=READS)
async def get_document_status(agent_id: Id, document_id: Id) -> dict[str, Any]:
    """Show whether CrowdSmart has extracted the text of an uploaded document.

    Use it when upload_document returned "processing". "status" is "pending" or
    "processing", then "completed" (with the number of passages) or "failed"
    (with the error).

    Args:
        agent_id: Knowledge Agent ID.
        document_id: Document ID, from upload_document.
    """
    return await api.call("GET", f"{AGENTS}/{agent_id}/documents/{document_id}/status")


@mcp.tool(annotations=ADDS)
async def add_text_document(
    agent_id: Id,
    title: str,
    text: str,
    source_url: str | None = None,
    author: str | None = None,
    timestamp: str | None = None,
    source_type: str | None = None,
) -> dict[str, Any]:
    """Add text to a Knowledge Agent you own, as a new document that keeps its source.

    The text is split into passages and can be asked about at once. The source
    details are stored with every passage, for citations.

    Args:
        agent_id: ID of a Knowledge Agent you own.
        title: Document title, shown in citations.
        text: The text to add.
        source_url: URL of the original source.
        author: Author of the original source.
        timestamp: ISO 8601 date when the source was published or created.
        source_type: Kind of source, for example "web", "note", "transcript" or "email".
    """
    body = {
        "title": title,
        "text": text,
        "source_url": source_url,
        "author": author,
        "timestamp": timestamp,
        "source_type": source_type,
    }
    return await api.call("POST", f"{AGENTS}/{agent_id}/text", json=body)


@mcp.tool(annotations=CHANGES)
async def delete_document(agent_id: Id, document_id: Id) -> dict[str, Any]:
    """Delete a document from a Knowledge Agent you own. This cannot be undone.

    To fix a damaged document, delete it, then upload the original file again.

    Args:
        agent_id: ID of a Knowledge Agent you own.
        document_id: Document ID, from list_documents.
    """
    return await api.call("DELETE", f"{AGENTS}/{agent_id}/documents/{document_id}")


@mcp.tool(annotations=READS)
async def check_corpus_quality(agent_id: Id) -> dict[str, Any]:
    """Find damaged documents in a Knowledge Agent's corpus, with a recommended fix for each.

    Damaged text makes an agent miss topics its documents hold. The check flags
    text broken one word per line, garbled OCR, words split by stray spaces and
    near-duplicate documents. It returns a summary and the flagged documents only.
    "unrecorded_uploads" lists uploads that stopped after storing passages but
    before recording the document: the agent does not use them, so upload the
    file again.

    Args:
        agent_id: Knowledge Agent ID.
    """
    report = await api.call("GET", f"{AGENTS}/{agent_id}/corpus-quality")
    flagged = [
        document
        for document in report["documents"]
        if document["severity"] != "healthy"
    ]
    return {
        "summary": report["summary"],
        "flagged": flagged,
        "unrecorded_uploads": report.get("unrecorded_uploads") or [],
    }
