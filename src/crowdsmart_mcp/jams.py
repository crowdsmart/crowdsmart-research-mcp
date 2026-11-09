"""Jam tools: run a Jam of Knowledge Agents (and people) and read the results.

A Jam asks its participants to respond to prompts, then to review each other's responses.
These tools run a Jam the way the current app does: the Jam Builder's plan creates a
draft, and launch opens it. Knowledge Agents then take part in the background, and people
take part in the app. These tools act as the owner of the API key, and only a Jam's
creator can launch it or add agents.
"""

import asyncio
from typing import Any, Literal, NotRequired, TypedDict

from mcp.server.mcpserver.exceptions import ToolError

from crowdsmart_mcp import api
from crowdsmart_mcp.api import ADDS, READS, Id
from crowdsmart_mcp.app import mcp


@mcp.tool(annotations=READS)
async def list_jams(community_id: str | None = None) -> dict[str, Any]:
    """List the active Jams you can see: those you created, those you take part in, and public ones.

    "relation" is "created", "contributing", "public" (you can join) or
    "invited_pending". Your own drafts are not listed until you launch them.

    Args:
        community_id: Only the Jams of this community, from list_my_communities.
    """
    user = await api.me()
    params = {"user_id": user["user_id"]}
    if community_id is not None:
        params["community_id"] = community_id
    result = await api.call("GET", "/api/collaborations/active", params=params)
    return {"jams": [_jam_summary(jam) for jam in result["collaborations"]]}


def _jam_summary(jam: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": jam["id"],
        "title": jam["title"],
        "description": jam.get("description"),
        "relation": jam["type"],
        "creator_name": jam.get("creator_name"),
        "created_at": jam["created_at"],
        "public": jam.get("is_public"),
    }


@mcp.tool(annotations=READS)
async def get_jam(jam_id: Id) -> dict[str, Any]:
    """Show a Jam: its description, status and prompts in order.

    Each prompt shows whether it asks for a probability, and the shortest reasoning
    it accepts. The Jam's creator also sees its invitees and the agents chosen
    for the draft ("agent_ids").

    Args:
        jam_id: Jam ID, from list_jams or create_jam.
    """
    user, jam, questions = await asyncio.gather(
        api.me(),
        api.call("GET", f"/api/jams/{jam_id}"),
        api.call("GET", f"/api/jams/{jam_id}/questions"),
    )
    prompts = sorted(questions["questions"], key=lambda prompt: prompt["order_index"])
    result = {
        "id": jam_id,
        "title": jam["title"],
        "description": jam["description"],
        "status": jam["status"],
        "creator_name": jam.get("creator_name"),
        "prompts": [
            {
                "order": prompt["order_index"],
                "type": prompt["prompt_type"],
                "text": prompt["text"],
                "description": prompt.get("description"),
                "requires_probability": prompt["require_probability"],
                "min_reasoning_length": prompt.get("min_reasoning_length") or 0,
            }
            for prompt in prompts
        ],
    }
    if jam["creator_id"] == user["user_id"]:
        result["invited_emails"] = jam["invited_emails"]
        result["agent_ids"] = jam["selected_agents"]
    return result


class JamPrompt(TypedDict):
    """One prompt of a Jam plan."""

    text: str
    type: NotRequired[Literal["prediction", "reasoning", "qualitative", "evaluation"]]
    seed_reasons: NotRequired[list[str]]


class JamMaterial(TypedDict):
    """Reading material that participants see with the prompts."""

    name: str
    content: str


@mcp.tool(annotations=ADDS)
async def create_jam(
    title: str,
    prompts: list[JamPrompt],
    description: str = "",
    decision_goal: str = "",
    expected_output: str = "",
    audience: str = "",
    assumptions: list[str] | None = None,
    materials: list[JamMaterial] | None = None,
    invite_emails: list[str] | None = None,
    agent_ids: list[str] | None = None,
    public: bool = False,
    community_id: str | None = None,
) -> dict[str, Any]:
    """Create a draft Jam from a plan. Nothing is sent until you launch it with launch_jam.

    Participants respond to each prompt in order, then review each other's
    responses. A "prediction" prompt (the default) asks for a probability and
    reasoning. A "reasoning", "qualitative" or "evaluation" prompt asks for
    reasoning only. Seed reasons are example ideas that participants review
    from the start. The result has the draft's green_room_url, where you can
    review and edit it in the app.

    A Jam can have Knowledge Agents only: give agent_ids and no invite_emails.
    Knowledge Agents answer only the first prompt, so give a Jam of agents one
    prompt, and use one Jam for each question.

    Args:
        title: The Jam's title.
        prompts: The prompts, in order: text, optional type and seed_reasons.
        description: What the Jam is about.
        decision_goal: The decision or learning the Jam serves.
        expected_output: The result that you want from the Jam.
        audience: Who takes part.
        assumptions: Assumptions that participants must know.
        materials: Reading material: each a name and its text.
        invite_emails: Email addresses of the people to invite at launch.
        agent_ids: Knowledge Agents that take part, from create_knowledge_agent
            or list_knowledge_agents. They start when the Jam launches.
        public: Whether anyone can find and join the Jam.
        community_id: The Jam's community, from list_my_communities.
    """
    user = await api.me()
    plan = {
        "title": title,
        "description": description,
        "decision_goal": decision_goal,
        "expected_output": expected_output,
        "audience_notes": audience,
        "assumptions": assumptions or [],
        "materials": materials or [],
        "prompts": [
            {
                "order": order,
                "prompt_type": prompt.get("type", "prediction"),
                "text": prompt["text"],
                "seed_reasons": prompt.get("seed_reasons", []),
            }
            for order, prompt in enumerate(prompts)
        ],
        "invited_emails": invite_emails or [],
        "selected_agent_ids": agent_ids or [],
        "is_public": public,
        "community_id": community_id,
    }
    body = {"plan": plan, "creator_id": user["user_id"]}
    return await api.call("POST", "/api/jams/build-from-plan", json=body)


async def _jam_you_created(jam_id: str, action: str) -> dict[str, Any]:
    """The Jam, if the key's account created it."""
    user = await api.me()
    jam = await api.call("GET", f"/api/jams/{jam_id}")
    if jam["creator_id"] != user["user_id"]:
        raise ToolError(f"Only the Jam's creator can {action}.")
    return jam


@mcp.tool(annotations=ADDS)
async def launch_jam(jam_id: Id, send_invitations: bool = True) -> dict[str, Any]:
    """Launch a draft Jam you created. This cannot be undone.

    The Jam becomes active, and each invitee gets an invitation email. You, the
    creator, are always invited too, and also get the email. Its Knowledge
    Agents start in the background: every agent responds to the first prompt,
    then reviews the other responses. An agent whose documents do not cover the
    prompt abstains, unless it allows general-knowledge backfill. Follow them
    with get_jam_results. Check the draft with get_jam first.

    Args:
        jam_id: ID of a draft Jam you created.
        send_invitations: Send the invitation emails, yours included (default true).
    """
    jam = await _jam_you_created(jam_id, "launch it")
    # A launch cannot be undone, so check the status before the launch request.
    if jam["status"] != "draft":
        raise ToolError(
            f"Jam {jam_id} is {jam['status']}: only a draft can be launched."
        )
    body = {
        "agent_ids": jam["selected_agents"],
        "participant_emails": jam["invited_emails"],
        "send_emails": send_invitations,
        "engage_agents": True,
    }
    return await api.call("POST", f"/api/jams/{jam_id}/launch", json=body)


@mcp.tool(annotations=ADDS)
async def add_agents_to_jam(jam_id: Id, agent_ids: list[str]) -> dict[str, Any]:
    """Have Knowledge Agents take part in an active Jam you created.

    The agents start in the background, as at a launch: every agent responds to
    the first prompt, then reviews the other responses. Follow them with
    get_jam_results.

    Args:
        jam_id: ID of an active Jam you created.
        agent_ids: Knowledge Agent IDs, from list_knowledge_agents.
    """
    _ = await _jam_you_created(jam_id, "add agents")
    path = f"/api/jams/{jam_id}/activate-agents"
    return await api.call("POST", path, json={"agent_ids": agent_ids})


@mcp.tool(annotations=READS)
async def get_jam_results(jam_id: Id) -> dict[str, Any]:
    """Show a Jam's results: participation, mean probabilities and top ideas.

    "funnel" counts what has happened so far, not whether the Jam is done: the
    participants (people and agents), the participants who responded, the
    responses, the reviewers and the reviews. An agent that fails or abstains
    adds nothing. To follow your agents, compare the author_id of each response
    in get_jam_responses with the agent IDs you gave. "prompts" gives
    each prompt's number of responses and, for a prediction prompt, the mean
    probability. "top_ideas" are the five most relevant responses.

    Args:
        jam_id: Jam ID.
    """
    return await api.call("GET", f"/api/jams/{jam_id}/summary")


def _response(proposition: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = proposition.get("metadata") or {}
    return {
        "id": proposition["proposition_id"],
        "prompt_order": proposition["prompt_order"],
        "author": proposition["contributor_name"],
        "author_id": proposition.get("contributor_id"),
        "author_type": proposition.get("participant_type"),
        "probability": proposition.get("contributor_rating"),
        "text": proposition["text"],
        "citations": api.citations(metadata.get("citations")),
    }


@mcp.tool(annotations=READS)
async def get_jam_responses(
    jam_id: Id, prompt_order: int | None = None
) -> dict[str, Any]:
    """Read the responses in a Jam: who wrote each one, its probability, text and citations.

    Use it to see what each Knowledge Agent said. "author_id" is the agent's ID.
    A citation such as [1] in the text is citation 1 of the response: read its
    document with read_document(author_id, document_id). The seed ideas of the
    Jam's plan have the author_type "seed". "probability" is the author's
    estimate, for a prediction prompt.

    Args:
        jam_id: Jam ID.
        prompt_order: Only the responses to this prompt (the first is 0), from get_jam.
    """
    params: dict[str, int] = (
        {} if prompt_order is None else {"prompt_order": prompt_order}
    )
    result = await api.call("GET", f"/api/jams/{jam_id}/propositions", params=params)
    return {"responses": [_response(p) for p in result["propositions"]]}
