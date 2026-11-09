"""Knowledge Model Agent (KMA) tools: domains and cases, building a KMA's models, forecasts.

A KMA forecasts the cases of one domain. A domain is a kind of decision: an outcome with
its states, and the profile fields that describe a case. A case is one question in the
domain, with an as-of date and a resolution criterion. A KMA is a Knowledge Agent that
holds one or more perspective models: Bayesian belief networks built from its domain
sources in a staged build that the owner approves. A forecast reads the case's evidence
through CrowdSmart's pinned reader. Its model calls run on CrowdSmart's worker, so reading
results arrive later. These tools follow the KMA page of the current app.
"""

import asyncio
from typing import Any, Literal, NotRequired, TypedDict

from mcp.server.mcpserver.exceptions import ToolError

from crowdsmart_mcp import api
from crowdsmart_mcp.api import ADDS, CHANGES, QUEUES, READS, Id
from crowdsmart_mcp.app import mcp

DOMAINS = "/api/kma/v2/domains"


def _kma(agent_id: str) -> str:
    return f"/api/knowledge-agents/{agent_id}/kma"


# ---------------------------------------------------------------------------------------
# Domains and cases
# ---------------------------------------------------------------------------------------


@mcp.tool(annotations=READS)
async def list_kma_domains() -> dict[str, Any]:
    """List every KMA domain: its outcome, number of cases and the KMAs that work on it.

    "yours" marks the domains you own. Only a domain's owner, or the owner of a KMA
    attached to it, adds cases to it.
    """
    user, result = await asyncio.gather(api.me(), api.call("GET", DOMAINS))
    return {
        "domains": [
            {
                "id": domain["id"],
                "name": domain["name"],
                "yours": domain["owner"] == user["user_id"],
                "outcome": domain["outcome"],
                "cases": domain["cases"],
                "kma_ids": domain["kmas"],
            }
            for domain in result["domains"]
        ]
    }


def _base_rate_summary(base_rate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not base_rate:
        return None
    table: dict[str, Any] = base_rate.get("table") or {}
    rows: list[Any] = table.get("rows") or []
    return {
        "table_id": table.get("table_id"),
        "version": table.get("version"),
        "rows": len(rows),
        "rules": base_rate.get("rules"),
        "cell_fields": base_rate.get("cell_fields"),
    }


@mcp.tool(annotations=READS)
async def get_kma_domain(domain_id: Id) -> dict[str, Any]:
    """Show a KMA domain: its outcome, profile fields, base-rate table, cases and KMAs.

    Each case shows its question, profile, as-of date, resolution criterion and,
    once decided, its resolution or why it is not scored. "practice" cases are
    forecast and resolved like the others but never scored. The base-rate table
    is summarized: its rules and number of rows.

    Args:
        domain_id: Domain ID, from list_kma_domains.
    """
    user, state = await asyncio.gather(
        api.me(), api.call("GET", f"{DOMAINS}/{domain_id}")
    )
    domain = state["domain"]
    return {
        "id": domain["id"],
        "name": domain["name"],
        "description": domain.get("description"),
        "yours": domain["owner"] == user["user_id"],
        "outcome": domain["outcome"],
        "profile_fields": domain["profile_fields"],
        "template_fields": domain.get("template_fields") or [],
        "base_rate": _base_rate_summary(domain.get("base_rate")),
        "cases": [
            {
                "case_id": case["case_id"],
                "title": case["title"],
                "question": case["question"],
                "as_of": case["as_of"],
                "profile": case["profile"],
                "bindings": case.get("bindings") or {},
                "resolution_criterion": case["resolution_criterion"],
                "practice": case.get("practice", False),
                "resolution": case.get("resolution"),
                "not_scored": case.get("unscored"),
            }
            for case in state["cases"].values()
        ],
        "kma_ids": state["kmas"],
    }


class DomainOutcome(TypedDict):
    """The outcome that the domain's cases forecast."""

    key: str
    definition: str
    states: list[str]
    target: NotRequired[str | None]


class ProfileField(TypedDict):
    """A field that describes each case of the domain."""

    type: Literal["enum", "enum_list", "bool", "int", "text", "date", "record_list"]
    description: str
    values: NotRequired[list[Any]]
    required: NotRequired[bool]
    nullable: NotRequired[bool]
    min: NotRequired[int]
    record: NotRequired[dict[str, Any]]


@mcp.tool(annotations=ADDS)
async def create_kma_domain(
    name: str,
    outcome: DomainOutcome,
    profile_fields: dict[str, ProfileField],
    description: str = "",
    template_fields: list[str] | None = None,
    base_rate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a KMA domain that you own: a kind of decision, with its outcome and case profile.

    Add its cases with add_kma_case, and attach KMAs to it with create_kma. A
    domain cannot be renamed or deleted here.

    Args:
        name: The domain's name. It must be new among your domains.
        outcome: key (lower case, for example "approved_by_goal_date"), definition
            (exactly what each state means, edge cases included), states (two to
            four lower-case keys) and target (the state of interest; required for
            a base-rate table).
        profile_fields: The fields that describe a case, by key. Each has a type,
            a description, "values" for enum and enum_list, and "required"
            (default true).
        description: What the domain covers.
        template_fields: Keys of the text bindings that each case must give.
        base_rate: A reviewed base-rate table section (kma.reference_table.v1:
            table, rules, cell_fields, theta_grid, population), for a two-state
            outcome. Without one, each forecast starts from the model's elicited
            prior and says so.
    """
    body: dict[str, Any] = {
        "name": name,
        "description": description,
        "outcome": outcome,
        "profile_fields": profile_fields,
        "template_fields": template_fields or [],
    }
    if base_rate is not None:
        body["base_rate"] = base_rate
    result = await api.call("POST", DOMAINS, json=body)
    return {"id": result["id"], "name": result["domain"]["name"]}


@mcp.tool(annotations=ADDS)
async def add_kma_case(
    domain_id: Id,
    case_id: str,
    title: str,
    question: str,
    as_of: str,
    resolution_criterion: str,
    profile: dict[str, Any] | None = None,
    bindings: dict[str, str] | None = None,
    practice: bool = False,
) -> dict[str, Any]:
    """Add a case to a KMA domain: one question that resolves from a public record.

    A case cannot be changed or removed once added. Evidence for it is admitted
    only if it was published on or before the as-of date.

    Args:
        domain_id: A domain you own, or one that a KMA of yours is attached to.
        case_id: The case's ID: letters, digits, _ or - (at most 60).
        title: A short title.
        question: The question, for example "Will the FDA approve X by 30 October 2026?".
        as_of: ISO date (YYYY-MM-DD): the last publication date of admitted evidence.
        resolution_criterion: Exactly how the case resolves to each outcome state,
            with its source.
        profile: The case's values of the domain's profile fields.
        bindings: The text bindings that the domain's template_fields name.
        practice: A rehearsal case: forecast, frozen and resolved, but never scored.
            Fixed when the case is added.
    """
    body = {
        "case_id": case_id,
        "title": title,
        "question": question,
        "as_of": as_of,
        "resolution_criterion": resolution_criterion,
        "profile": profile or {},
        "bindings": bindings or {},
        "practice": practice,
    }
    return await api.call("POST", f"{DOMAINS}/{domain_id}/cases", json=body)


@mcp.tool(annotations=ADDS)
async def resolve_kma_case(
    domain_id: Id, case_id: Id, state: str, source: str, date: str
) -> dict[str, Any]:
    """Record a case's outcome. This cannot be undone or changed.

    Frozen forecasts of the case are then scored (get_kma_scoreboard). A KMA whose
    forecast was surprised by the outcome can raise needs (list_kma_needs).

    Args:
        domain_id: A domain you own.
        case_id: An open case of the domain.
        state: The outcome: one of the domain's outcome states.
        source: Where the outcome was announced, for example a URL.
        date: ISO date (YYYY-MM-DD) of the decision.
    """
    path = f"{DOMAINS}/{domain_id}/cases/{case_id}/resolve"
    result = await api.call(
        "POST", path, json={"state": state, "source": source, "date": date}
    )
    return {
        "resolution": result["case"]["resolution"],
        "needs_raised": result["surprise"],
    }


@mcp.tool(annotations=ADDS)
async def mark_kma_case_unscored(
    domain_id: Id, case_id: Id, reason: str
) -> dict[str, Any]:
    """Mark a case as not scored, with the reason. This cannot be undone.

    Use it when the decision was announced before the case's forecasts were
    frozen: such a forecast would not be a forecast.

    Args:
        domain_id: A domain you own.
        case_id: An open case of the domain.
        reason: Why the case is not scored.
    """
    path = f"{DOMAINS}/{domain_id}/cases/{case_id}/unscored"
    result = await api.call("POST", path, json={"reason": reason})
    return {"case_id": case_id, "not_scored": result["case"]["unscored"]}


@mcp.tool(annotations=READS)
async def get_kma_scoreboard(domain_id: Id) -> dict[str, Any]:
    """Score a domain's frozen forecasts against the resolved cases, by KMA.

    For each KMA: hits, Brier score and log loss, the same scores for its forecast
    before reading (base rate and fixed facts only), and the cases missed or not
    scored. Only forecasts frozen before resolution count. Compare a panel with
    the base rate and with its best member: the members' mean always gains over
    disagreeing members, so that gain alone is not evidence of skill.

    Args:
        domain_id: Domain ID, from list_kma_domains.
    """
    return await api.call("GET", f"{DOMAINS}/{domain_id}/scoreboard")


# ---------------------------------------------------------------------------------------
# KMAs and their sources
# ---------------------------------------------------------------------------------------


@mcp.tool(annotations=READS)
async def list_kmas() -> dict[str, Any]:
    """List the KMAs you own, in all your communities, with their domains.

    A KMA is also a Knowledge Agent: ask_knowledge_agent answers from its
    documents, and the document tools manage them.
    """
    user = await api.me()
    communities, domains = await asyncio.gather(
        api.my_communities(user["user_id"]), api.call("GET", DOMAINS)
    )
    lists = await asyncio.gather(
        *(
            api.call(
                "GET",
                "/api/knowledge-model-agents",
                params={"community_id": community["id"]},
            )
            for community in communities["communities"]
        )
    )
    domain_of = {
        agent_id: domain["id"]
        for domain in domains["domains"]
        for agent_id in domain["kmas"]
    }
    kmas: list[dict[str, Any]] = []
    for community, listed in zip(communities["communities"], lists, strict=True):
        for agent in listed["agents"]:
            kmas.append(
                {
                    "id": agent["id"],
                    "name": agent["name"],
                    "community_id": community["id"],
                    "domain_id": domain_of.get(agent["id"]),
                    "documents": len(agent["documents"]),
                    "created_at": agent.get("created_at"),
                }
            )
    return {"kmas": kmas}


@mcp.tool(annotations=ADDS)
async def create_kma(
    name: str,
    perspective: str,
    domain_id: str | None = None,
    community_id: str | None = None,
) -> dict[str, Any]:
    """Create a KMA that you own, as the app's New KMA does, and optionally attach it to a domain.

    The KMA is a private Knowledge Agent with no documents. A KMA works on one
    domain: the domain's jobs act on every KMA attached to it, and the
    attachment cannot be undone here. To build its model:

    1. Add its domain sources with add_text_document or upload_document.
    2. Approve each extraction with review_kma_document.
    3. Tag each one with tag_kma_document.
    4. Start the build with start_kma_build.

    Args:
        name: The KMA's name; by convention it ends in "KMA".
        perspective: One sentence: what this KMA reads for.
        domain_id: The domain to attach it to, from list_kma_domains. Omit to
            attach later with attach_kma_to_domain.
        community_id: The workspace (community) the KMA belongs to, from
            list_my_communities. Default: your default community.
    """
    user = await api.me()
    community = community_id or await api.default_community(user["user_id"])
    body = {
        "user_id": user["user_id"],
        "name": name,
        "expertise_headline": name,
        "system_prompt": perspective,
        "strict_rag": True,
        "generation_mode": "foundation_assisted",
        "allow_foundation_backfill": False,
        "community_id": community,
    }
    created = await api.call("POST", "/api/knowledge-agents/", json=body)
    agent_id = created["agent_id"]
    try:
        _ = await api.call(
            "POST", f"{_kma(agent_id)}/enable", json={"community_id": community}
        )
        if domain_id is not None:
            _ = await attach_kma_to_domain(agent_id, domain_id)
    except ToolError as error:
        raise ToolError(
            f"Created Knowledge Agent {agent_id}, but could not finish making it a KMA "
            + f"({error}). Do not create it again: retry the step that failed for {agent_id}."
        ) from error
    return {
        "agent_id": agent_id,
        "name": created["name"],
        "community_id": community,
        "domain_id": domain_id,
    }


@mcp.tool(annotations=ADDS)
async def attach_kma_to_domain(agent_id: Id, domain_id: str) -> dict[str, Any]:
    """Attach a KMA you own to a domain. This cannot be undone here.

    A KMA works on one domain, and the domain's jobs act on every KMA attached to
    it. Check the domain's name first.

    Args:
        agent_id: ID of a KMA you own, from list_kmas or create_kma.
        domain_id: Domain ID, from list_kma_domains.
    """
    return await api.call(
        "POST", f"{_kma(agent_id)}/v2/domain", json={"domain": domain_id}
    )


def _kma_document(
    document: dict[str, Any], tag: dict[str, Any] | None
) -> dict[str, Any]:
    extraction = document["extraction"]
    review = document["review"]
    return {
        "id": document["id"],
        "filename": document["filename"],
        "created_at": document.get("created_at"),
        "extraction": extraction["status"],
        "issues": extraction["issues"],
        "passages": len(extraction["blocks"]),
        "extraction_digest": document.get("extraction_digest"),
        "review": {
            key: review.get(key)
            for key in ("state", "notes", "reviewer_id", "created_at")
            if key in review
        },
        "tag": None
        if tag is None
        else {key: tag.get(key) for key in ("role", "case_id", "published")},
    }


@mcp.tool(annotations=READS)
async def list_kma_documents(agent_id: Id) -> dict[str, Any]:
    """List a KMA's documents with their extraction review and their tag.

    A KMA reads only documents whose extraction is approved ("review.state" is
    "approved") and that are tagged: as a domain source (role "domain", used to
    build its models) or as evidence for one case (role "case"). "published"
    decides admission: case evidence counts only if published by the case's
    as-of date. "extraction_digest" identifies the extraction that
    review_kma_document approves. Read a document's text with read_document.

    Args:
        agent_id: KMA ID, from list_kmas.
    """
    view, tags = await asyncio.gather(
        api.call("GET", _kma(agent_id)),
        api.call("GET", f"{_kma(agent_id)}/v2/documents/tags"),
    )
    return {
        "domain_id": tags["domain"],
        "documents": [
            _kma_document(document, tags["tags"].get(document["id"]))
            for document in view["documents"]
        ],
    }


@mcp.tool(annotations=CHANGES)
async def review_kma_document(
    agent_id: Id,
    document_id: Id,
    decision: Literal["approved", "needs_correction"],
    extraction_digest: str,
    full_document_checked: bool = False,
    notes: str = "",
) -> dict[str, Any]:
    """Record your review of a KMA document's extracted text. It replaces an earlier review.

    Approve a document only when the user has checked the full extracted text
    (read_document) against the original and says so: "approved" requires
    full_document_checked. "needs_correction" requires notes that say what is
    wrong and where. The review applies to the extraction with this digest: if
    the document changed, review it again. When every document of the KMA is
    approved, CrowdSmart also starts its older concept and network generation,
    which makes model calls.

    Args:
        agent_id: ID of a KMA you own.
        document_id: Document ID, from list_kma_documents.
        decision: "approved" or "needs_correction".
        extraction_digest: The document's extraction_digest from list_kma_documents.
        full_document_checked: The user confirms that the full extraction was checked
            against the original.
        notes: What was checked, or what needs correcting (at most 4000 characters).
    """
    body = {
        "decision": decision,
        "notes": notes,
        "full_document_checked": full_document_checked,
        "extraction_digest": extraction_digest,
    }
    path = f"{_kma(agent_id)}/documents/{document_id}/review"
    view = await api.call("POST", path, json=body)
    review = next(d["review"] for d in view["documents"] if d["id"] == document_id)
    return {"document_id": document_id, "review": review}


@mcp.tool(annotations=CHANGES)
async def tag_kma_document(
    agent_id: Id,
    document_id: Id,
    role: Literal["domain", "case"],
    published: str,
    case_id: str | None = None,
) -> dict[str, Any]:
    """Tag a KMA document as a domain source or as evidence for one case. It replaces an earlier tag.

    The KMA must be attached to a domain. Domain sources build its models: tag
    them before start_kma_build, since a build keeps the sources it started
    with. Case evidence is read by every KMA of the domain when it forecasts
    that case. Only approved documents are read.

    Args:
        agent_id: ID of a KMA you own.
        document_id: Document ID, from list_kma_documents.
        role: "domain" (a domain source) or "case" (evidence for case_id).
        published: ISO date (YYYY-MM-DD) when the document was published. Case
            evidence is admitted only if published by the case's as-of date.
        case_id: The case, for role "case".
    """
    body: dict[str, Any] = {"role": role, "published": published}
    if case_id is not None:
        body["case_id"] = case_id
    path = f"{_kma(agent_id)}/v2/documents/{document_id}/tag"
    tag = await api.call("POST", path, json=body)
    return {
        "document_id": document_id,
        **{k: tag.get(k) for k in ("role", "case_id", "published")},
    }


# ---------------------------------------------------------------------------------------
# Building a KMA's perspective models
# ---------------------------------------------------------------------------------------


@mcp.tool(annotations=READS)
async def check_kma_build_preflight(agent_id: Id) -> dict[str, Any]:
    """Check whether a KMA is ready for a build, before start_kma_build.

    The checks cover the reader, the worker, the queue, the domain and the domain
    sources, with each source's share of the passages (a source above 40% can
    dominate the proposals). "ok" is false while any check is an error. It also
    gives the build settings and the estimated number of proposal calls.

    Args:
        agent_id: ID of a KMA you own.
    """
    return await api.call("GET", f"{_kma(agent_id)}/v2/build/preflight")


@mcp.tool(annotations=ADDS)
async def start_kma_build(
    agent_id: Id,
    perspective: str,
    brief: str | None = None,
    copy_from: str | None = None,
) -> dict[str, Any]:
    """Start building one perspective model of a KMA from its tagged, approved domain sources.

    Run check_kma_build_preflight first. The build then moves through stages:

    1. The reader proposes variables.
    2. You choose them.
    3. Their definitions are written.
    4. A structure is proposed, and you check it.
    5. The parameters are elicited.
    6. You publish the perspective.

    The model calls run on CrowdSmart's worker, so follow the build with
    get_kma_builds and act with decide_kma_build when it waits for you. One
    build per perspective can be open at a time. The build keeps the sources it
    started with.

    Args:
        agent_id: ID of a KMA you own, attached to a domain.
        perspective: The perspective's name: lower-case letters, digits and
            underscores, for example "clinical_trialist".
        brief: What the perspective reads for, at most 600 characters: what the
            target state means, what moves toward it and what moves against it.
            It is sent with every proposal. End it with: "Propose variables that
            a single press release, filing or report about one case could state."
        copy_from: An earlier build ID whose chosen variables and wording are
            shown ticked again (you still accept them).
    """
    body: dict[str, Any] = {"perspective": perspective}
    if brief is not None:
        body["brief"] = brief
    if copy_from is not None:
        body["copy_from"] = copy_from
    return _build(await api.call("POST", f"{_kma(agent_id)}/v2/build", json=body))


def _build(state: dict[str, Any]) -> dict[str, Any]:
    """A build's state. Once the variables are chosen, the proposals are only listed."""
    stages: dict[str, Any] = state.get("stages") or {}
    s1: dict[str, Any] | None = stages.get("S1")
    if s1 is None or state.get("stage") == "S1_variables":
        return state
    proposals: list[dict[str, Any]] = s1.get("proposals") or []
    summary = {"proposed": [p["key"] for p in proposals], "calls": s1.get("calls")}
    return {**state, "stages": {**stages, "S1": summary}}


@mcp.tool(annotations=QUEUES)
async def get_kma_builds(agent_id: Id) -> dict[str, Any]:
    """Show a KMA's builds: each one's stage, what it waits for, and what you decide from.

    "awaiting" names the decision that a build waits for:
    - "accept_variables": choose four to six of stages.S1.proposals, rewording
      each definition to refer to one case before the decision.
    - "accept_definitions": accept stages.S2.definitions.
    - "accept_structure": check stages.S3 (parents, polarity and link votes).
    - "publish" or "take_published": publish the perspective (stages.S4 shows
      the elicited answers and incoherent rows).
    - "stop_or_restart": the structure failed its checks; stop the build or
      revise it from the variables.
    "awaiting" is null while "waiting" calls are with CrowdSmart's worker. Asking
    works out each build's state, which queues any model calls it now needs.
    "published" shows the KMA's published perspectives, and "worker" the
    worker's last report.

    Args:
        agent_id: ID of a KMA you own.
    """
    status = await api.call("GET", f"{_kma(agent_id)}/v2/build")
    return {
        "domain": status["domain"],
        "reader": status["reader"],
        "worker": status["worker"],
        "domain_sources": status["domain_sources"],
        "published": status["published"],
        "builds": [_build(build) for build in status["builds"]],
    }


BuildAction = Literal[
    "accept_variables",
    "accept_definitions",
    "accept_structure",
    "publish",
    "stop",
    "revise",
]


@mcp.tool(annotations=CHANGES)
async def decide_kma_build(
    agent_id: Id,
    build_id: Id,
    action: BuildAction,
    accept: list[str] | bool | None = None,
    edits: dict[str, str] | None = None,
    parents: dict[str, list[str]] | None = None,
    polarity: dict[str, Literal["positive", "negative", "unknown"]] | None = None,
) -> dict[str, Any]:
    """Make the owner's decision at a stage of a KMA build. Decide only as the user decides.

    Each action applies only when get_kma_builds shows the build "awaiting" it:
    - "accept_variables": accept is the list of chosen proposal keys (four to
      six); edits rewords their definitions (10 to 400 characters each).
    - "accept_definitions": accept is the list of definition keys to keep; edits
      as above.
    - "accept_structure": accept true (or false to stop the build). parents,
      optional, replaces the structure: each variable and the outcome with their
      parents, at most three each, and every variable must reach the outcome.
      polarity sets link signs, keyed "parent->child".
    - "publish": the perspective joins the KMA's published model, and readings
      of the domain's open cases are queued.
    - "stop": end the build. This cannot be undone.
    - "revise": stop the build and start a new one at the variables, with its
      choices carried over (the result is the new build).

    Args:
        agent_id: ID of a KMA you own.
        build_id: Build ID, from get_kma_builds (for example "b1").
        action: The decision.
        accept: The accepted keys, or true or false for accept_structure.
        edits: New definitions, by variable key.
        parents: The structure that you set, for accept_structure.
        polarity: Link signs, for accept_structure.
    """
    path = f"{_kma(agent_id)}/v2/build/{build_id}"
    if action == "revise":
        return _build(await api.call("POST", f"{path}/revise", json={}))
    body: dict[str, Any] = {}
    if accept is not None:
        body["accept"] = accept
    if edits:
        body["edits"] = edits
    if parents is not None:
        body["parents"] = parents
    if polarity:
        body["polarity"] = polarity
    return _build(await api.call("POST", f"{path}/{action}", json=body))


# ---------------------------------------------------------------------------------------
# Forecasts
# ---------------------------------------------------------------------------------------


@mcp.tool(annotations=QUEUES)
async def get_kma_forecast(agent_id: Id, case_id: Id) -> dict[str, Any]:
    """Show a KMA's current forecast for a case of its domain, and why.

    "base_rate" is the starting probability (or "elicited" when the domain has
    no matching base-rate row). For each perspective model: "prior" (before
    reading), "forecast" (after reading) and "evidence": each reading of an
    admitted passage, with the variable, the state likelihoods, the source
    document and the quote. "average" is the KMA's forecast: the mean of its
    models. "admission" shows which documents were admitted or set aside, and
    why. "readings_waiting" counts passages not yet read: asking queues their
    readings on CrowdSmart's worker, so ask again later. The forecast counts
    only once frozen (freeze_kma_forecast).

    Args:
        agent_id: KMA ID, from list_kmas or a domain's kma_ids.
        case_id: A case of the KMA's domain, from get_kma_domain.
    """
    belief = await api.call("GET", f"{_kma(agent_id)}/v2/cases/{case_id}/belief")
    if not belief["published"]:
        return {"published": False}
    return {
        "published": True,
        "domain_id": belief["domain"],
        "case_id": case_id,
        "average": belief["average"],
        "base_rate": belief["base_rate"],
        "perspectives": belief["perspectives"],
        "facts": belief["facts"],
        "admission": belief["admission"],
        "readings_waiting": belief["readings_waiting"],
        "readings_failed": belief["readings_failed"],
        "readings_rejected": belief["readings_rejected"],
        "complete": belief["complete"],
    }


@mcp.tool(annotations=READS)
async def get_kma_model(agent_id: Id) -> dict[str, Any]:
    """Show a KMA's published models: each perspective's network.

    For each perspective: its variables ("nodes") with their states, definitions
    and parents, the outcome's prior, and each variable's "relevance": how far
    that variable alone can move the outcome.

    Args:
        agent_id: KMA ID.
    """
    return await api.call("GET", f"{_kma(agent_id)}/v2/model")


@mcp.tool(annotations=ADDS)
async def freeze_kma_forecast(
    domain_id: Id, case_id: Id, agent_id: str
) -> dict[str, Any]:
    """Freeze a KMA's forecast for a case, before the case resolves. This cannot be undone.

    Only frozen forecasts are scored, and a KMA freezes a case once. Freezing
    fails while readings are still waiting: check get_kma_forecast first. Failed
    or rejected readings count as no evidence and are recorded with the freeze.

    Args:
        domain_id: The KMA's domain.
        case_id: An open case of the domain.
        agent_id: ID of a KMA you own, attached to the domain.
    """
    path = f"{DOMAINS}/{domain_id}/cases/{case_id}/freeze"
    frozen = await api.call("POST", path, json={"agent": agent_id})
    keys = (
        "case_id",
        "agent",
        "distribution",
        "predicted",
        "before_reading",
        "before_predicted",
        "base_rate",
        "perspectives",
        "evidence",
        "facts",
        "failed_calls",
        "readings_rejected",
        "definition_version",
        "method_version",
    )
    return {key: frozen.get(key) for key in keys}


# ---------------------------------------------------------------------------------------
# Switches, needs and the domain's cohort
# ---------------------------------------------------------------------------------------


@mcp.tool(annotations=READS)
async def get_kma_switches(agent_id: Id) -> dict[str, Any]:
    """Show a KMA's adaptive switches, and every change with who made it and why.

    "counts": learn from each resolved case. "predict": record a prediction
    before every observation. "lessons": draft a lesson from each surprise.
    "notify": send its questions to people. "sending" says whether the server
    sends messages at all.

    Args:
        agent_id: ID of a KMA you own.
    """
    return await api.call("GET", f"{_kma(agent_id)}/v2/adaptive")


@mcp.tool(annotations=CHANGES)
async def set_kma_switch(
    agent_id: Id,
    switch: Literal["counts", "predict", "lessons", "notify"],
    on: bool,
    reason: str,
) -> dict[str, Any]:
    """Turn one of a KMA's adaptive switches on or off, with the reason.

    Set the switches that an experiment calls for before its first freeze, the
    same for every KMA of one arm. See get_kma_switches for what each switch does.

    Args:
        agent_id: ID of a KMA you own, with a published model.
        switch: "counts", "predict", "lessons" or "notify".
        on: The new setting.
        reason: Why it changes. Recorded with the change.
    """
    body = {"switch": switch, "on": on, "reason": reason}
    return await api.call("POST", f"{_kma(agent_id)}/v2/adaptive", json=body)


@mcp.tool(annotations=QUEUES)
async def list_kma_needs(agent_id: Id) -> dict[str, Any]:
    """List what a KMA would like people to answer ("needs"), and the questions asked so far.

    A need is raised by a build, a Jam round or a resolved case: for example a
    model row whose answers disagree, or a link the passages split on. Ask a
    need with ask_kma_need. Each question shows its wording (once CrowdSmart's
    worker has worded it), respondents, answer-by date, status and answers.

    Args:
        agent_id: ID of a KMA you own.
    """
    needs, questions = await asyncio.gather(
        api.call("GET", f"{_kma(agent_id)}/v2/needs"),
        api.call("GET", f"{_kma(agent_id)}/v2/questions"),
    )
    return {**needs, "questions": questions["questions"]}


@mcp.tool(annotations=ADDS)
async def ask_kma_need(
    agent_id: Id,
    need_id: Id,
    addressed_to: list[str],
    context: str = "none",
    answer_by: str | None = None,
) -> dict[str, Any]:
    """Ask a KMA's need of members of its domain's cohort.

    The question is worded on CrowdSmart's worker, then sent in CrowdSmart and by
    email, but only while the KMA's "notify" switch is on. Otherwise each message
    is recorded as a dry run. Only the people named can answer.

    Args:
        agent_id: ID of a KMA you own.
        need_id: An open need, from list_kma_needs.
        addressed_to: Account IDs of cohort members ("user_id" in get_kma_cohort).
        context: What context the question carries (default "none").
        answer_by: ISO date after today. Default: seven days from today.
    """
    body: dict[str, Any] = {"addressed_to": addressed_to, "context": context}
    if answer_by is not None:
        body["answer_by"] = answer_by
    return await api.call("POST", f"{_kma(agent_id)}/v2/needs/{need_id}/ask", json=body)


@mcp.tool(annotations=READS)
async def get_kma_cohort(domain_id: Id) -> dict[str, Any]:
    """Show a domain's cohort: the people invited to answer its KMAs' questions.

    Each person has a state ("invited", "member", "declined" or "removed"), why
    they were invited and, once a member, their account ID. "sends" gives each
    invitation email's outcome.

    Args:
        domain_id: A domain you own, or one that a KMA of yours is attached to.
    """
    return await api.call("GET", f"{DOMAINS}/{domain_id}/cohort")


@mcp.tool(annotations=ADDS)
async def invite_to_kma_cohort(domain_id: Id, email: str, why: str) -> dict[str, Any]:
    """Invite a person to a domain's cohort. CrowdSmart emails them an invitation.

    They accept by signing in with that email address. The email says why they
    were chosen. Invite only people the user names.

    Args:
        domain_id: A domain you own, or one that a KMA of yours is attached to.
        email: The person's email address.
        why: Why this person is invited. It is shown in the invitation.
    """
    path = f"{DOMAINS}/{domain_id}/cohort/invite"
    return await api.call("POST", path, json={"email": email, "why": why})


@mcp.tool(annotations=CHANGES)
async def remove_from_kma_cohort(domain_id: Id, email: str) -> dict[str, Any]:
    """Remove a person from a domain's cohort, or withdraw their invitation.

    Args:
        domain_id: A domain you own, or one that a KMA of yours is attached to.
        email: The person's email address, from get_kma_cohort.
    """
    path = f"{DOMAINS}/{domain_id}/cohort/remove"
    return await api.call("POST", path, json={"email": email})
