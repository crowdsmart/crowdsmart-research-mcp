"""Tests for the Knowledge Model Agent tools, through an MCP client and a fake API."""

import json

import httpx2
import pytest

from tests.helpers import USER_ID, FakeApi, call_tool, error_text, ok, sent

pytestmark = pytest.mark.anyio

DOMAINS = "/api/kma/v2/domains"
KMA = "/api/knowledge-agents/a1/kma"
OUTCOME = {
    "key": "rate_decision",
    "definition": "What the bank does to its policy rate.",
    "states": ["hike", "hold", "cut"],
    "target": None,
}


def domain_summary(did: str, owner: str, kmas: list[str]) -> dict[str, object]:
    """A domain as GET /api/kma/v2/domains lists it."""
    return {
        "id": did,
        "name": did.title(),
        "owner": owner,
        "outcome": OUTCOME,
        "cases": 1,
        "kmas": kmas,
    }


def kma_view(documents: list[dict[str, object]]) -> dict[str, object]:
    """A KMA as GET .../kma (and the review route) returns it."""
    return {
        "id": "a1",
        "name": "Rates KMA",
        "created_at": "2026-11-09T00:00:00",
        "documents": documents,
        "learning_enabled": False,
    }


def kma_document(review: str = "unreviewed") -> dict[str, object]:
    return {
        "id": "d1",
        "filename": "Policy explainer",
        "byte_count": 0,
        "created_at": "2026-11-09T00:00:00",
        "extraction_digest": "abc123",
        "review": {"state": review, "id": None},
        "extraction": {
            "status": "review_required",
            "issues": [],
            "blocks": [
                {"location": {"kind": "passage", "index": 1}, "text": "One."},
                {"location": {"kind": "passage", "index": 2}, "text": "Two."},
            ],
        },
    }


async def test_list_kma_domains_marks_yours(api: FakeApi):
    routes, _ = api
    routes["GET", DOMAINS] = ok(
        {
            "domains": [
                domain_summary("rates", USER_ID, ["a1"]),
                domain_summary("fda", "someone-else", []),
            ]
        }
    )

    result = await call_tool("list_kma_domains")

    domains = result.structured_content["domains"]
    assert [(d["id"], d["yours"], d["kma_ids"]) for d in domains] == [
        ("rates", True, ["a1"]),
        ("fda", False, []),
    ]


async def test_get_kma_domain_summarizes_the_base_rate_table(api: FakeApi):
    routes, _ = api
    base_rate = {
        "table": {"table_id": "t", "version": "1", "rows": [{"row_id": "E1"}] * 40},
        "rules": [{"id": "r_all", "when": {"x": ["a"]}, "quantity": "q"}],
        "cell_fields": {},
        "theta_grid": {"t1": 0.5},
    }
    case = {
        "case_id": "c1",
        "title": "October",
        "question": "Hike, hold or cut?",
        "as_of": "2026-10-26",
        "profile": {"with_mpr": True},
        "bindings": {},
        "resolution_criterion": "The press release.",
        "practice": True,
        "resolution": None,
        "unscored": None,
    }
    routes["GET", f"{DOMAINS}/rates"] = ok(
        {
            "domain": {
                "id": "rates",
                "name": "Rates",
                "owner": USER_ID,
                "outcome": OUTCOME,
                "profile_fields": {},
                "template_fields": [],
                "base_rate": base_rate,
                "description": "d",
            },
            "cases": {"c1": case},
            "kmas": ["a1"],
        }
    )

    result = await call_tool("get_kma_domain", domain_id="rates")

    content = result.structured_content
    assert content["yours"] is True
    assert content["base_rate"] == {
        "table_id": "t",
        "version": "1",
        "rows": 40,
        "rules": base_rate["rules"],
        "cell_fields": {},
    }
    assert content["subject_field"] is None
    assert content["cases"][0]["practice"] is True
    assert content["cases"][0]["not_scored"] is None


async def test_create_kma_domain_omits_an_absent_base_rate(api: FakeApi):
    routes, requests = api
    routes["POST", DOMAINS] = ok({"id": "rates_1a2b3c", "domain": {"name": "Rates"}})
    fields = {"with_mpr": {"type": "bool", "description": "an MPR is released"}}

    result = await call_tool(
        "create_kma_domain", name="Rates", outcome=OUTCOME, profile_fields=fields
    )

    assert result.structured_content == {"id": "rates_1a2b3c", "name": "Rates"}
    assert sent(requests, "POST", DOMAINS) == {
        "name": "Rates",
        "description": "",
        "outcome": OUTCOME,
        "profile_fields": fields,
        "template_fields": [],
    }


async def test_create_kma_domain_sends_its_subject_field(api: FakeApi):
    routes, requests = api
    routes["POST", DOMAINS] = ok({"id": "fda_1a2b3c", "domain": {"name": "FDA"}})
    fields = {"drug": {"type": "text", "description": "the drug under review"}}

    _ = await call_tool(
        "create_kma_domain",
        name="FDA",
        outcome=OUTCOME,
        profile_fields=fields,
        subject_field="drug",
    )

    assert sent(requests, "POST", DOMAINS)["subject_field"] == "drug"


async def test_set_kma_case_profile_returns_the_case(api: FakeApi):
    routes, requests = api
    path = f"{DOMAINS}/fda/cases/c1/profile"
    case = {
        "case_id": "c1",
        "title": "Orforglipron",
        "question": "Approved by 15 April?",
        "as_of": "2026-03-31",
        "profile": {"drug": "orforglipron"},
        "bindings": {},
        "resolution_criterion": "The FDA's letter.",
        "practice": False,
        "resolution": None,
        "unscored": None,
    }
    routes["POST", path] = ok({"case": case})

    result = await call_tool(
        "set_kma_case_profile",
        domain_id="fda",
        case_id="c1",
        field="drug",
        value="orforglipron",
    )

    assert sent(requests, "POST", path) == {"field": "drug", "value": "orforglipron"}
    content = result.structured_content
    assert content["profile"] == {"drug": "orforglipron"}
    assert content["not_scored"] is None


async def test_create_kma_makes_an_agent_a_kma_on_its_domain(api: FakeApi):
    routes, requests = api
    routes["GET", "/api/communities/mine"] = ok(
        {"default_community_id": "c1", "communities": []}
    )
    routes["POST", "/api/knowledge-agents/"] = ok(
        {"success": True, "agent_id": "a1", "name": "Rates KMA", "message": ""}
    )
    routes["POST", f"{KMA}/enable"] = ok(kma_view([]))
    routes["POST", f"{KMA}/v2/domain"] = ok({"domain": "rates"})

    result = await call_tool(
        "create_kma",
        name="Rates KMA",
        perspective="Reads for inflation.",
        domain_id="rates",
    )

    assert result.structured_content == {
        "agent_id": "a1",
        "name": "Rates KMA",
        "community_id": "c1",
        "domain_id": "rates",
    }
    created = sent(requests, "POST", "/api/knowledge-agents/")
    assert created["system_prompt"] == "Reads for inflation."
    assert created["expertise_headline"] == "Rates KMA"
    assert (created["generation_mode"], created["allow_foundation_backfill"]) == (
        "foundation_assisted",
        False,
    )
    assert sent(requests, "POST", f"{KMA}/enable") == {"community_id": "c1"}
    assert sent(requests, "POST", f"{KMA}/v2/domain") == {"domain": "rates"}


async def test_create_kma_keeps_the_agent_id_when_a_later_step_fails(api: FakeApi):
    routes, requests = api
    routes["POST", "/api/knowledge-agents/"] = ok(
        {"success": True, "agent_id": "a1", "name": "Rates KMA", "message": ""}
    )
    routes["POST", f"{KMA}/enable"] = ok(kma_view([]))
    routes["POST", f"{KMA}/v2/domain"] = httpx2.Response(
        409, json={"detail": "unknown domain nope"}
    )

    result = await call_tool(
        "create_kma",
        name="Rates KMA",
        perspective="p",
        domain_id="nope",
        community_id="c1",
    )

    message = error_text(result)
    assert "Created KMA a1" in message
    assert "unknown domain nope" in message
    assert "Do not create it again" in message
    assert "attach_kma_to_domain" in message
    assert len([r for r in requests if r.url.path == "/api/knowledge-agents/"]) == 1


async def test_create_kma_names_enable_kma_when_enabling_fails(api: FakeApi):
    routes, requests = api
    routes["POST", "/api/knowledge-agents/"] = ok(
        {"success": True, "agent_id": "a1", "name": "Rates KMA", "message": ""}
    )
    routes["POST", f"{KMA}/enable"] = httpx2.Response(503, json={"detail": "busy"})

    result = await call_tool(
        "create_kma",
        name="Rates KMA",
        perspective="p",
        domain_id="rates",
        community_id="c1",
    )

    message = error_text(result)
    assert "Created Knowledge Agent a1" in message
    assert "busy" in message
    assert "call enable_kma for a1, then attach_kma_to_domain" in message
    assert not [r for r in requests if r.url.path == f"{KMA}/v2/domain"]


@pytest.mark.parametrize(
    ("arguments", "body"),
    [({}, {"community_id": None}), ({"community_id": "c2"}, {"community_id": "c2"})],
)
async def test_enable_kma_makes_an_existing_agent_a_kma(
    api: FakeApi, arguments: dict[str, str], body: dict[str, object]
):
    routes, requests = api
    routes["POST", f"{KMA}/enable"] = ok(kma_view([kma_document()]))

    result = await call_tool("enable_kma", agent_id="a1", **arguments)

    assert result.structured_content == {
        "agent_id": "a1",
        "name": "Rates KMA",
        "documents": 1,
    }
    assert sent(requests, "POST", f"{KMA}/enable") == body


async def test_list_kmas_reads_every_community_and_finds_each_domain(api: FakeApi):
    routes, requests = api
    routes["GET", "/api/communities/mine"] = ok(
        {
            "default_community_id": "c1",
            "communities": [{"id": "c1", "name": "One"}, {"id": "c2", "name": "Two"}],
        }
    )
    routes["GET", DOMAINS] = ok({"domains": [domain_summary("rates", USER_ID, ["a1"])]})

    def by_community(request: httpx2.Request) -> httpx2.Response:
        if request.url.params["community_id"] == "c1":
            return ok({"agents": [kma_view([kma_document()])]})
        return ok({"agents": []})

    routes["GET", "/api/knowledge-model-agents"] = by_community

    result = await call_tool("list_kmas")

    assert result.structured_content == {
        "kmas": [
            {
                "id": "a1",
                "name": "Rates KMA",
                "community_id": "c1",
                "domain_id": "rates",
                "documents": 1,
                "created_at": "2026-11-09T00:00:00",
            }
        ]
    }
    listed = [r for r in requests if r.url.path == "/api/knowledge-model-agents"]
    assert sorted(r.url.params["community_id"] for r in listed) == ["c1", "c2"]


async def test_list_kma_documents_gives_review_tag_and_digest(api: FakeApi):
    routes, _ = api
    routes["GET", KMA] = ok(kma_view([kma_document()]))
    routes["GET", f"{KMA}/v2/documents/tags"] = ok(
        {
            "domain": "rates",
            "tags": {
                "d1": {
                    "role": "case",
                    "case_id": "c1",
                    "published": "2026-09-02",
                    "by": USER_ID,
                }
            },
        }
    )

    result = await call_tool("list_kma_documents", agent_id="a1")

    assert result.structured_content == {
        "domain_id": "rates",
        "documents": [
            {
                "id": "d1",
                "filename": "Policy explainer",
                "created_at": "2026-11-09T00:00:00",
                "extraction": "review_required",
                "issues": [],
                "passages": 2,
                "extraction_digest": "abc123",
                "review": {"state": "unreviewed"},
                "tag": {"role": "case", "case_id": "c1", "published": "2026-09-02"},
            }
        ],
    }


def extraction_document(texts: list[str]) -> dict[str, object]:
    """A document whose extraction blocks have these texts, from stored passages 1, 3, 5..."""
    document = kma_document()
    document["extraction"] = {
        "status": "review_required",
        "issues": [],
        "blocks": [
            {"location": {"kind": "passage", "index": 2 * i + 1}, "text": text}
            for i, text in enumerate(texts)
        ],
    }
    return document


async def test_read_kma_extraction_gives_the_blocks_and_the_digest(api: FakeApi):
    routes, requests = api
    routes["GET", KMA] = ok(kma_view([extraction_document(["aaaa", "bbbb", "cc"])]))

    result = await call_tool(
        "read_kma_extraction", agent_id="a1", document_id="d1", max_chars=9
    )

    assert result.structured_content == {
        "document_id": "d1",
        "filename": "Policy explainer",
        "extraction": "review_required",
        "issues": [],
        "extraction_digest": "abc123",
        "review": {"state": "unreviewed"},
        "total_passages": 3,
        "passages": [
            {"location": {"kind": "passage", "index": 1}, "text": "aaaa"},
            {"location": {"kind": "passage", "index": 3}, "text": "bbbb"},
        ],
        "truncated": False,
        "next_start": 3,
    }
    # The text and the digest come from one read.
    assert [r.url.path for r in requests] == [KMA]


async def test_read_kma_extraction_continues_from_start(api: FakeApi):
    routes, _ = api
    routes["GET", KMA] = ok(kma_view([extraction_document(["aaaa", "bbbb", "cc"])]))

    result = await call_tool(
        "read_kma_extraction", agent_id="a1", document_id="d1", start=3
    )

    assert result.structured_content is not None
    assert result.structured_content["passages"] == [
        {"location": {"kind": "passage", "index": 5}, "text": "cc"}
    ]
    assert result.structured_content["next_start"] is None


async def test_read_kma_extraction_cuts_a_passage_longer_than_max_chars(api: FakeApi):
    routes, _ = api
    routes["GET", KMA] = ok(kma_view([extraction_document(["a" * 10, "b"])]))

    result = await call_tool(
        "read_kma_extraction", agent_id="a1", document_id="d1", max_chars=4
    )

    assert result.structured_content is not None
    assert result.structured_content["passages"] == [
        {"location": {"kind": "passage", "index": 1}, "text": "aaaa"}
    ]
    assert result.structured_content["truncated"] is True
    assert result.structured_content["next_start"] == 2


async def test_read_kma_extraction_of_an_unknown_document(api: FakeApi):
    routes, _ = api
    routes["GET", KMA] = ok(kma_view([kma_document()]))

    result = await call_tool("read_kma_extraction", agent_id="a1", document_id="d9")

    assert "has no document d9" in error_text(result)


async def test_review_kma_document_sends_the_digest_and_the_attestation(api: FakeApi):
    routes, requests = api
    path = f"{KMA}/documents/d1/review"
    routes["POST", path] = ok(kma_view([kma_document(review="approved")]))

    result = await call_tool(
        "review_kma_document",
        agent_id="a1",
        document_id="d1",
        decision="approved",
        extraction_digest="abc123",
        full_document_checked=True,
        notes="Checked against the PDF.",
    )

    assert result.structured_content == {
        "document_id": "d1",
        "review": {"state": "approved", "id": None},
    }
    assert sent(requests, "POST", path) == {
        "decision": "approved",
        "notes": "Checked against the PDF.",
        "full_document_checked": True,
        "extraction_digest": "abc123",
    }


async def test_review_kma_document_does_not_attest_by_default(api: FakeApi):
    routes, requests = api
    path = f"{KMA}/documents/d1/review"
    routes["POST", path] = httpx2.Response(
        409,
        json={
            "detail": "Confirm that the full extraction was checked against the original"
        },
    )

    result = await call_tool(
        "review_kma_document",
        agent_id="a1",
        document_id="d1",
        decision="approved",
        extraction_digest="abc123",
    )

    assert "Confirm that the full extraction was checked" in error_text(result)
    assert sent(requests, "POST", path)["full_document_checked"] is False


@pytest.mark.parametrize(
    ("arguments", "body"),
    [
        (
            {"role": "domain", "published": "2026-11-09"},
            {"role": "domain", "published": "2026-11-09"},
        ),
        (
            {"role": "case", "published": "2026-09-02", "case_id": "c1"},
            {"role": "case", "published": "2026-09-02", "case_id": "c1"},
        ),
    ],
)
async def test_tag_kma_document(
    api: FakeApi, arguments: dict[str, str], body: dict[str, str]
):
    routes, requests = api
    path = f"{KMA}/v2/documents/d1/tag"
    routes["POST", path] = ok(
        {
            "role": body["role"],
            "case_id": body.get("case_id"),
            "published": body["published"],
            "by": USER_ID,
        }
    )

    result = await call_tool(
        "tag_kma_document", agent_id="a1", document_id="d1", **arguments
    )

    assert sent(requests, "POST", path) == body
    assert result.structured_content == {
        "document_id": "d1",
        "role": body["role"],
        "case_id": body.get("case_id"),
        "published": body["published"],
    }


async def test_start_kma_build_sends_only_what_is_given(api: FakeApi):
    routes, requests = api
    routes["POST", f"{KMA}/v2/build"] = ok({"build": "b1", "stage": "S1_variables"})

    result = await call_tool(
        "start_kma_build", agent_id="a1", perspective="inflation_outlook", brief="b"
    )

    assert result.structured_content == {"build": "b1", "stage": "S1_variables"}
    assert sent(requests, "POST", f"{KMA}/v2/build") == {
        "perspective": "inflation_outlook",
        "brief": "b",
    }


@pytest.mark.parametrize(
    ("arguments", "path", "body"),
    [
        (
            {
                "action": "accept_variables",
                "accept": ["a", "b"],
                "edits": {"a": "x" * 12},
            },
            "/b1/accept_variables",
            {"accept": ["a", "b"], "edits": {"a": "x" * 12}},
        ),
        (
            {
                "action": "accept_structure",
                "accept": True,
                "parents": {"rate_decision": ["a"], "a": []},
                "polarity": {"a->rate_decision": "positive"},
            },
            "/b1/accept_structure",
            {
                "accept": True,
                "parents": {"rate_decision": ["a"], "a": []},
                "polarity": {"a->rate_decision": "positive"},
            },
        ),
        (
            {"action": "accept_structure", "accept": False},
            "/b1/accept_structure",
            {"accept": False},
        ),
        ({"action": "publish"}, "/b1/publish", {}),
        ({"action": "stop"}, "/b1/stop", {}),
        ({"action": "revise"}, "/b1/revise", {}),
    ],
)
async def test_decide_kma_build_posts_each_action(
    api: FakeApi, arguments: dict[str, object], path: str, body: dict[str, object]
):
    routes, requests = api
    routes["POST", f"{KMA}/v2/build{path}"] = ok({"build": "b1", "stage": "S2"})

    result = await call_tool(
        "decide_kma_build", agent_id="a1", build_id="b1", **arguments
    )

    assert not result.is_error
    assert sent(requests, "POST", f"{KMA}/v2/build{path}") == body


async def test_decide_kma_build_never_fills_in_a_missing_accept(api: FakeApi):
    routes, requests = api
    refusal = (
        "accept_structure needs accept: true; to reject the structure, "
        + "stop or revise the build"
    )
    routes["POST", f"{KMA}/v2/build/b1/accept_structure"] = httpx2.Response(
        409, json={"detail": refusal}
    )

    result = await call_tool(
        "decide_kma_build", agent_id="a1", build_id="b1", action="accept_structure"
    )

    assert sent(requests, "POST", f"{KMA}/v2/build/b1/accept_structure") == {}
    assert error_text(result).endswith(f"CrowdSmart API error 409: {refusal}")


async def test_get_kma_builds_leaves_out_refits_and_revisions(api: FakeApi):
    routes, _ = api
    routes["GET", f"{KMA}/v2/build"] = ok(
        {
            "reader_registered": True,
            "reader": {"model": "m"},
            "domain": {"id": "rates"},
            "builds": [{"build": "b1", "awaiting": "accept_variables"}],
            "refits": [{"r": 1}],
            "revisions": [],
            "published": None,
            "domain_sources": 54,
            "worker": {"state": "watching"},
        }
    )

    result = await call_tool("get_kma_builds", agent_id="a1")

    assert result.structured_content == {
        "domain": {"id": "rates"},
        "reader": {"model": "m"},
        "worker": {"state": "watching"},
        "domain_sources": 54,
        "published": None,
        "builds": [{"build": "b1", "awaiting": "accept_variables"}],
    }


async def test_kma_build_lists_proposals_once_the_variables_are_chosen(api: FakeApi):
    routes, _ = api
    proposal = {"key": "inflation_trend", "definition": "d", "states": ["a", "b"]}
    s1 = {"proposals": [proposal], "rejected": [], "calls": 7, "topics": []}

    def build(stage: str) -> dict[str, object]:
        return {"build": "b1", "stage": stage, "stages": {"S1": s1, "S2": {"x": 1}}}

    routes["GET", f"{KMA}/v2/build"] = ok(
        {
            "reader": None,
            "domain": None,
            "builds": [build("S1_variables"), build("S2_definitions")],
            "published": None,
            "domain_sources": 0,
            "worker": None,
        }
    )

    result = await call_tool("get_kma_builds", agent_id="a1")

    choosing, later = result.structured_content["builds"]
    assert choosing["stages"]["S1"] == s1
    assert later["stages"] == {
        "S1": {"proposed": ["inflation_trend"], "calls": 7},
        "S2": {"x": 1},
    }


async def test_get_kma_forecast_before_a_model_is_published(api: FakeApi):
    routes, _ = api
    routes["GET", f"{KMA}/v2/cases/c1/belief"] = ok({"published": False})

    result = await call_tool("get_kma_forecast", agent_id="a1", case_id="c1")

    assert result.structured_content == {"published": False}


async def test_freeze_kma_forecast_leaves_out_the_recorded_inputs(api: FakeApi):
    routes, requests = api
    path = f"{DOMAINS}/rates/cases/c1/freeze"
    frozen = {
        "action": "freeze",
        "case_id": "c1",
        "agent": "a1",
        "distribution": {"hike": 0.2, "hold": 0.7, "cut": 0.1},
        "predicted": "hold",
        "inputs_snapshot": {"calls": {"x": "y" * 10_000}},
        "seq": 9,
    }
    routes["POST", path] = ok(frozen)

    result = await call_tool(
        "freeze_kma_forecast", domain_id="rates", case_id="c1", agent_id="a1"
    )

    content = result.structured_content
    assert "inputs_snapshot" not in content
    assert content["distribution"] == frozen["distribution"]
    assert sent(requests, "POST", path) == {"agent": "a1"}


async def test_resolve_kma_case_returns_the_resolution_and_raised_needs(api: FakeApi):
    routes, requests = api
    path = f"{DOMAINS}/rates/cases/c1/resolve"
    resolution = {
        "state": "hike",
        "source": "https://example.org",
        "date": "2026-10-28",
    }
    routes["POST", path] = ok({"case": {"resolution": resolution}, "surprise": []})

    result = await call_tool(
        "resolve_kma_case",
        domain_id="rates",
        case_id="c1",
        state="hike",
        source="https://example.org",
        date="2026-10-28",
    )

    assert result.structured_content == {"resolution": resolution, "needs_raised": []}
    assert sent(requests, "POST", path) == {
        "state": "hike",
        "source": "https://example.org",
        "date": "2026-10-28",
    }


async def test_list_kma_needs_adds_the_questions(api: FakeApi):
    routes, _ = api
    routes["GET", f"{KMA}/v2/needs"] = ok(
        {
            "needs": [{"id": "need_1", "status": "open"}],
            "wordings_waiting": 0,
            "policy": "manual",
        }
    )
    routes["GET", f"{KMA}/v2/questions"] = ok({"questions": [{"id": "q1"}]})

    result = await call_tool("list_kma_needs", agent_id="a1")

    assert result.structured_content == {
        "needs": [{"id": "need_1", "status": "open"}],
        "wordings_waiting": 0,
        "policy": "manual",
        "questions": [{"id": "q1"}],
    }


async def test_ask_kma_need_defaults_the_answer_by_date_upstream(api: FakeApi):
    routes, requests = api
    path = f"{KMA}/v2/needs/need_1/ask"
    routes["POST", path] = ok({"input": 3, "questions": [], "notified": 0})

    _ = await call_tool(
        "ask_kma_need", agent_id="a1", need_id="need_1", addressed_to=["u2"]
    )

    assert sent(requests, "POST", path) == {"addressed_to": ["u2"], "context": "none"}


@pytest.mark.parametrize(
    ("tool", "arguments", "method", "path", "body"),
    [
        (
            "get_kma_scoreboard",
            {"domain_id": "rates"},
            "GET",
            f"{DOMAINS}/rates/scoreboard",
            None,
        ),
        ("get_kma_model", {"agent_id": "a1"}, "GET", f"{KMA}/v2/model", None),
        ("get_kma_switches", {"agent_id": "a1"}, "GET", f"{KMA}/v2/adaptive", None),
        (
            "get_kma_cohort",
            {"domain_id": "rates"},
            "GET",
            f"{DOMAINS}/rates/cohort",
            None,
        ),
        (
            "check_kma_build_preflight",
            {"agent_id": "a1"},
            "GET",
            f"{KMA}/v2/build/preflight",
            None,
        ),
        (
            "attach_kma_to_domain",
            {"agent_id": "a1", "domain_id": "rates"},
            "POST",
            f"{KMA}/v2/domain",
            {"domain": "rates"},
        ),
        (
            "add_kma_case",
            {
                "domain_id": "rates",
                "case_id": "c1",
                "title": "t",
                "question": "q",
                "as_of": "2026-10-26",
                "resolution_criterion": "r",
            },
            "POST",
            f"{DOMAINS}/rates/cases",
            {
                "case_id": "c1",
                "title": "t",
                "question": "q",
                "as_of": "2026-10-26",
                "resolution_criterion": "r",
                "profile": {},
                "bindings": {},
                "practice": False,
            },
        ),
        (
            "invite_to_kma_cohort",
            {"domain_id": "rates", "email": "grace@example.com", "why": "an expert"},
            "POST",
            f"{DOMAINS}/rates/cohort/invite",
            {"email": "grace@example.com", "why": "an expert"},
        ),
        (
            "remove_from_kma_cohort",
            {"domain_id": "rates", "email": "grace@example.com"},
            "POST",
            f"{DOMAINS}/rates/cohort/remove",
            {"email": "grace@example.com"},
        ),
    ],
)
async def test_kma_tools_call_their_route(
    api: FakeApi,
    tool: str,
    arguments: dict[str, object],
    method: str,
    path: str,
    body: dict[str, object] | None,
):
    routes, requests = api
    routes[method, path] = ok({"done": True})

    result = await call_tool(tool, **arguments)

    assert result.structured_content == {"done": True}
    if body is not None:
        assert sent(requests, method, path) == body


async def test_mark_kma_case_unscored_returns_the_reason(api: FakeApi):
    routes, requests = api
    path = f"{DOMAINS}/rates/cases/c1/unscored"
    reason = {"reason": "decided before the freeze", "by": USER_ID}
    routes["POST", path] = ok({"case": {"unscored": reason}})

    result = await call_tool(
        "mark_kma_case_unscored",
        domain_id="rates",
        case_id="c1",
        reason="decided before the freeze",
    )

    assert result.structured_content == {"case_id": "c1", "not_scored": reason}
    assert sent(requests, "POST", path) == {"reason": "decided before the freeze"}


async def test_set_kma_switch_sends_the_reason(api: FakeApi):
    routes, requests = api
    routes["POST", f"{KMA}/v2/adaptive"] = ok(
        {"switches": {"counts": True}, "history": [], "sending": False}
    )

    _ = await call_tool(
        "set_kma_switch", agent_id="a1", switch="counts", on=True, reason="arm B"
    )

    assert json.loads(requests[-1].content) == {
        "switch": "counts",
        "on": True,
        "reason": "arm B",
    }


async def test_unknown_switch_sends_no_request(api: FakeApi):
    _, requests = api

    result = await call_tool(
        "set_kma_switch", agent_id="a1", switch="kar", on=True, reason="r"
    )

    assert result.is_error
    assert requests == []
