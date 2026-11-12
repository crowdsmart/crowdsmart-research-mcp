"""What the tool modules share: API calls and errors, the key's account, safety hints,
the path-ID type and the citation shape."""

import os
from typing import Annotated, Any, cast

import httpx2
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

API_URL = os.environ.get("CROWDSMART_API_URL", "https://csgcip.onrender.com")
TIMEOUT = 120.0  # generative answers can take up to a minute

MISSING_KEY = (
    "CROWDSMART_API_KEY is not set. Create a key in CrowdSmart (User Dashboard, API Key) "
    "and pass it in the MCP client's server environment."
)

# Safety hints, from what each tool does to CrowdSmart (not from its HTTP method).
READS = ToolAnnotations(read_only_hint=True)
ADDS = ToolAnnotations(read_only_hint=False, destructive_hint=False)
# Replaces or deletes something: settings, a document, a review or a build.
CHANGES = ToolAnnotations(read_only_hint=False, destructive_hint=True)
# Changes nothing that you see, but can record derived state and queue model calls
# on CrowdSmart's worker. Asking again queues nothing new.
QUEUES = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True
)

# An ID that goes into a URL path: a UUID, or a KMA domain, case or build ID.
# Letters, digits, hyphens and underscores only, so an ID cannot change the path,
# the query or the operation.
Id = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+$")]


async def call(method: str, path: str, **kwargs: Any) -> Any:
    """Call the CrowdSmart API and return its JSON body. Raise ToolError on failure."""
    headers = {"Authorization": f"Bearer {os.environ['CROWDSMART_API_KEY']}"}
    async with httpx2.AsyncClient(
        base_url=API_URL, headers=headers, timeout=TIMEOUT
    ) as client:
        try:
            response = await client.request(method, path, **kwargs)
        except httpx2.HTTPError as error:
            raise ToolError(
                f"Could not reach CrowdSmart at {API_URL}: {error!r}"
            ) from error
    # Redirects are not followed, so a redirect is an error too.
    if not response.is_success:
        raise ToolError(
            f"CrowdSmart API error {response.status_code}: {_error_detail(response)}"
        )
    try:
        return response.json()
    except ValueError as error:
        body = response.text[:300]
        raise ToolError(
            f"CrowdSmart API returned a body that is not JSON: {body}"
        ) from error


def _error_detail(response: httpx2.Response) -> str:
    """The API's own error message, or the start of the body (for example a firewall page)."""
    try:
        detail = response.json()["detail"]
        if isinstance(detail, list):  # request validation errors, one per field
            errors = cast(list[Any], detail)
            return "; ".join(
                f"{'.'.join(map(str, error['loc']))}: {error['msg']}"
                for error in errors
            )
        return str(detail)
    except (ValueError, KeyError, TypeError):
        return response.text[:300]


def citations(
    raw: list[dict[str, Any]] | None, verbose: bool = False
) -> list[dict[str, Any]]:
    """The citations of an answer or a Jam response: [n] in the text is citation n.

    verbose adds the passage's chunk_id and its retrieval scores.
    """
    result: list[dict[str, Any]] = []
    for citation in raw or []:
        item = {
            "index": citation.get("index"),
            "document": citation.get("source"),
            "document_id": citation.get("document_id"),
            "excerpt": citation.get("excerpt"),
        }
        if verbose:
            item["chunk_id"] = citation.get("chunk_id")
            item["similarity"] = citation.get("similarity")
            item["relevance_probability"] = citation.get("relevance_probability")
        result.append(item)
    return result


async def me() -> dict[str, Any]:
    """The account that owns the API key: its user_id, name and email."""
    return await call("GET", "/api/human-auth/me")


async def my_communities(user_id: str) -> dict[str, Any]:
    """The communities the user belongs to, and the user's default community."""
    return await call(
        "GET", "/api/communities/mine", params={"participant_id": user_id}
    )


async def default_community(user_id: str) -> str | None:
    """The user's default community: the app creates agents in it."""
    return (await my_communities(user_id))["default_community_id"]
