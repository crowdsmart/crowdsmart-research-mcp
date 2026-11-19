"""Correct one fact of a KMA without a rebuild, and repair a model built from a withdrawn source.

A correction is a new record with the reason and the person who made it. CrowdSmart
rewrites no sealed record, and a frozen forecast never changes: a correction can change
only its score. Each correction that has a preview returns, by default, the report of
what it would change and writes nothing. Write a correction only when the owner has
accepted that report. A source document cannot be taken out of a perspective that was
built from it, so a source repair builds each such perspective again from the remaining
sources.
"""

from typing import Any

from crowdsmart_mcp import api
from crowdsmart_mcp.api import ADDS, CHANGES, READS, Id
from crowdsmart_mcp.app import mcp
from crowdsmart_mcp.kmas import DOMAINS


def _v2(agent_id: str) -> str:
    return f"/api/knowledge-agents/{agent_id}/kma/v2"


# ---------------------------------------------------------------------------------------
# A case's outcome
# ---------------------------------------------------------------------------------------


@mcp.tool(annotations=CHANGES)
async def correct_kma_case_outcome(
    domain_id: Id,
    case_id: Id,
    state: str,
    source: str,
    date: str,
    reason: str,
    replaces: int,
    preview: bool = True,
) -> dict[str, Any]:
    """Correct the recorded outcome of a resolved case.

    With preview (the default), nothing is written. The reply is the report of
    what the correction changes, for each KMA of the domain: the score of its
    frozen forecast before and after (null when it froze none), the need made
    void with its questions closed, the lesson withdrawn or kept, whether the
    corrected outcome surprises it, and what its learning does. Show the
    report. Call again with preview false only when the domain's owner has
    accepted it in the conversation. The earlier outcome stays in the case's
    "resolution_history" (get_kma_domain). A frozen forecast never changes:
    only its score does. CrowdSmart refuses a correction that changes nothing:
    to correct only the source or the date, send the same state. When the
    correction is written, CrowdSmart starts a refit for each KMA whose
    "counts" switch is on, and publishes it when its readings are done.

    Args:
        domain_id: A domain you own.
        case_id: A resolved case of the domain.
        state: The correct outcome: one of the domain's outcome states.
        source: Where the outcome was announced, for example a URL.
        date: ISO date (YYYY-MM-DD) of the decision.
        reason: Why the recorded outcome was wrong.
        replaces: The case's "resolved_at" from get_kma_domain: the outcome in
            force. If the case was corrected since, CrowdSmart refuses: read it
            again.
        preview: Return the report and write nothing (default true).
    """
    body = {
        "state": state,
        "source": source,
        "date": date,
        "reason": reason,
        "replaces": replaces,
        "preview": preview,
    }
    path = f"{DOMAINS}/{domain_id}/cases/{case_id}/resolution/correct"
    return await api.call("POST", path, json=body)


@mcp.tool(annotations=CHANGES)
async def retract_kma_case_outcome(
    domain_id: Id, case_id: Id, reason: str, replaces: int, preview: bool = True
) -> dict[str, Any]:
    """Take back an outcome that was recorded on the wrong case. The case is then open again.

    An open case can be resolved again or marked not scored. The retracted
    outcome stays in the case's "resolution_history" (get_kma_domain). With
    preview (the default), nothing is written: the reply is the report of what
    the retraction changes, as for correct_kma_case_outcome. Call again with
    preview false only when the domain's owner has accepted it in the
    conversation.

    Args:
        domain_id: A domain you own.
        case_id: A resolved case of the domain.
        reason: Why the outcome does not belong to this case.
        replaces: The case's "resolved_at" from get_kma_domain.
        preview: Return the report and write nothing (default true).
    """
    body = {"reason": reason, "replaces": replaces, "preview": preview}
    path = f"{DOMAINS}/{domain_id}/cases/{case_id}/resolution/retract"
    return await api.call("POST", path, json=body)


@mcp.tool(annotations=READS)
async def get_kma_stale_outcomes(agent_id: Id) -> dict[str, Any]:
    """List what a KMA's models learned from outcomes since corrected or retracted. For the KMA's owner.

    "perspectives" lists each published perspective whose model was fitted on
    cases whose outcome changed since, with those cases. "frozen_forecasts"
    lists the forecasts frozen with such a model. A new refit puts a model
    right. When the KMA's "counts" switch is on ("counts_switch_on"),
    CrowdSmart starts that refit after a correction and publishes it when its
    readings are done. When the switch is off, no refit starts, and these tools
    cannot start one. A frozen forecast never changes. This report changes
    nothing.

    Args:
        agent_id: ID of a KMA you own.
    """
    return await api.call("GET", f"{_v2(agent_id)}/outcomes/stale")


# ---------------------------------------------------------------------------------------
# One reading of a passage
# ---------------------------------------------------------------------------------------


@mcp.tool(annotations=CHANGES)
async def set_aside_kma_reading(
    agent_id: Id, case_id: Id, call: str, reason: str, preview: bool = True
) -> dict[str, Any]:
    """Stop one reading from counting in a case's forecast.

    A reading is one recorded call to CrowdSmart's reader. Only a reading that
    the model made can be set aside. The call stays on record, and its reading
    stops counting wherever the call is used again. With preview (the
    default), nothing is written. The reply gives the case's forecast "before"
    and "after", the published perspectives now out of date and the frozen
    forecasts left as made. Call again with preview false only when the KMA's
    owner has accepted it in the conversation. restore_kma_reading makes the
    reading count again.

    Args:
        agent_id: ID of a KMA you own.
        case_id: The case.
        call: The "call" shown with the reading in get_kma_forecast.
        reason: Why the reading is wrong.
        preview: Return the report and write nothing (default true).
    """
    body = {"call": call, "reason": reason, "preview": preview}
    path = f"{_v2(agent_id)}/cases/{case_id}/readings/set-aside"
    return await api.call("POST", path, json=body)


@mcp.tool(annotations=CHANGES)
async def give_kma_reading(
    agent_id: Id,
    case_id: Id,
    passage: str,
    variable: str,
    state: str,
    reason: str,
    quote: str | None = None,
    preview: bool = True,
) -> dict[str, Any]:
    """Give the owner's own reading of one passage for one variable, in place of the model's.

    The state is one of the variable's states, with a quote from the passage
    that supports it, or "not_stated" with no quote. CrowdSmart refuses a quote
    that is not in the passage. The reading counts in the case's forecast as a
    stated reading. "not_stated" means that the passage says nothing about the
    variable, so the model's reading of it stops counting. A new reading of the
    same passage and variable replaces the earlier one. With preview (the
    default), nothing is written: the reply is the report, as for
    set_aside_kma_reading. Call again with preview false only when the KMA's
    owner has accepted it in the conversation. restore_kma_reading takes the
    reading back.

    Args:
        agent_id: ID of a KMA you own.
        case_id: The case.
        passage: The passage, as a reading in get_kma_forecast names it.
        variable: The variable, from get_kma_model.
        state: One of the variable's states, or "not_stated".
        reason: Why the model's reading is wrong.
        quote: The words of the passage that support the state. Omit it for
            "not_stated".
        preview: Return the report and write nothing (default true).
    """
    body: dict[str, Any] = {"passage": passage, "variable": variable, "state": state}
    if quote is not None:
        body["quote"] = quote
    body |= {"reason": reason, "preview": preview}
    path = f"{_v2(agent_id)}/cases/{case_id}/readings/state"
    return await api.call("POST", path, json=body)


@mcp.tool(annotations=CHANGES)
async def restore_kma_reading(
    agent_id: Id,
    case_id: Id,
    reason: str,
    call: str | None = None,
    passage: str | None = None,
    variable: str | None = None,
    preview: bool = True,
) -> dict[str, Any]:
    """Undo a reading correction: a reading set aside counts again, or the owner's own reading is taken back.

    Give call for a reading set aside, or passage and variable for the owner's
    own reading. With preview (the default), nothing is written: the reply is
    the report, as for set_aside_kma_reading. Call again with preview false
    only when the KMA's owner has accepted it in the conversation.

    Args:
        agent_id: ID of a KMA you own.
        case_id: The case.
        reason: Why the correction is undone.
        call: The call of the reading set aside.
        passage: The passage of the owner's reading.
        variable: The variable of the owner's reading.
        preview: Return the report and write nothing (default true).
    """
    body: dict[str, Any] = {"reason": reason}
    if call is not None:
        body["call"] = call
    if passage is not None:
        body["passage"] = passage
    if variable is not None:
        body["variable"] = variable
    body["preview"] = preview
    path = f"{_v2(agent_id)}/cases/{case_id}/readings/restore"
    return await api.call("POST", path, json=body)


@mcp.tool(annotations=CHANGES)
async def retry_kma_failed_call(
    agent_id: Id, case_id: Id, call: str, reason: str, preview: bool = True
) -> dict[str, Any]:
    """Ask CrowdSmart's worker to make a failed reading call again.

    The worker makes the same call with the next seed. Until it is recorded,
    the failed call stands: the forecast does not change, and a freeze does not
    wait. The forecast's "reading_corrections" then shows the retry as
    "waiting", "ok" or "failed". If the retry fails, its own call is in
    "failed_calls": to try again, name that call, not the first one. A call
    that succeeded cannot be made again, and a retry cannot be undone. With
    preview (the default), nothing is written or queued. Call again with
    preview false only when the KMA's owner has accepted it in the
    conversation.

    Args:
        agent_id: ID of a KMA you own.
        case_id: The case.
        call: A call from the forecast's "failed_calls" in get_kma_forecast.
        reason: Why the call is made again.
        preview: Return the report and write nothing (default true).
    """
    body = {"call": call, "reason": reason, "preview": preview}
    path = f"{_v2(agent_id)}/cases/{case_id}/readings/retry"
    return await api.call("POST", path, json=body)


@mcp.tool(annotations=READS)
async def get_kma_reading_corrections(agent_id: Id) -> dict[str, Any]:
    """List a KMA's reading corrections, and what they leave out of date. For the KMA's owner.

    "in_force" has the readings set aside, the owner's own readings and the
    retries. "no_longer_in_force" has the corrections since undone or
    replaced. The report also lists the published perspectives whose refit was
    fitted without the corrections, and the frozen forecasts made without
    them. A frozen forecast never changes. This report changes nothing.

    Args:
        agent_id: ID of a KMA you own.
    """
    return await api.call("GET", f"{_v2(agent_id)}/readings")


# ---------------------------------------------------------------------------------------
# A probability row, people's answers and revisions
# ---------------------------------------------------------------------------------------


@mcp.tool(annotations=ADDS)
async def state_kma_row(
    agent_id: Id,
    perspective: str,
    variable: str,
    probabilities: dict[str, float],
    reason: str,
    given: dict[str, str] | None = None,
) -> dict[str, Any]:
    """State the owner's value for one probability row of a published perspective, with the reason.

    The value is one voice on the row, beside the model's and other people's
    answers. It does not override them. Nothing is published:
    start_kma_revision shows the rows that the voices move. The reply gives
    the statement's position ("statement"), which withdraw_kma_answer names.
    You can have one statement in force on a row: withdraw it before you state
    a new value.

    Args:
        agent_id: ID of a KMA you own.
        perspective: A published perspective, from get_kma_model.
        variable: The row's variable.
        probabilities: The probability of each state of the variable, for
            example {"rising": 0.7}. For a variable with two states, one state
            is enough.
        reason: Where the value comes from.
        given: The row's parent condition: the state of each parent of the
            variable. Omit it for a variable with no parents.
    """
    body: dict[str, Any] = {"perspective": perspective, "variable": variable}
    if given is not None:
        body["given"] = given
    body |= {"probabilities": probabilities, "reason": reason}
    return await api.call("POST", f"{_v2(agent_id)}/rows/state", json=body)


@mcp.tool(annotations=CHANGES)
async def withdraw_kma_answer(
    agent_id: Id, reason: str, question: str | None = None, statement: int | None = None
) -> dict[str, Any]:
    """Withdraw an answer to a KMA's question, or a row statement, with the reason.

    A respondent can withdraw their own answer, and the KMA's owner can set any
    answer aside. The answer stays on record and counts for nothing from now
    on. This cannot be undone: a changed mind is a new answer or a new
    statement. Its question is open again; if its answer-by date has passed,
    CrowdSmart then closes it as unmet. A case fact leaves the live forecasts
    at once. A probability stays in the published model until a revision is
    published: "still_in" lists the perspectives that hold it. Give question or
    statement, not both.

    Args:
        agent_id: The KMA.
        reason: Why the answer is withdrawn.
        question: The question's ID, from list_kma_needs ("questions").
        statement: A row statement's position, from state_kma_row.
    """
    body: dict[str, Any] = {"reason": reason}
    if question is not None:
        body["question"] = question
    if statement is not None:
        body["statement"] = statement
    return await api.call("POST", f"{_v2(agent_id)}/answers/withdraw", json=body)


@mcp.tool(annotations=ADDS)
async def start_kma_revision(agent_id: Id, perspective: str) -> dict[str, Any]:
    """Start a revision of a published perspective: its model fitted again with the answers in force.

    The answers are people's answers to the KMA's parameter questions and the
    owner's row statements. A revision also takes out the answers withdrawn
    since ("dropped"). The reply is the preview: "rows_moved" (each row before
    and after), the outcome's prior "before" and "after", the "applied" and
    "skipped" answers, and the candidate "model" with its "sha256". Its
    "stage" is "review" when it can be published. Nothing is published:
    publish_kma_revision publishes it. CrowdSmart refuses when there is
    nothing to revise: no answer in force, or every answer already published.

    Args:
        agent_id: ID of a KMA you own.
        perspective: A published perspective, from get_kma_model.
    """
    body = {"perspective": perspective}
    return await api.call("POST", f"{_v2(agent_id)}/revise", json=body)


@mcp.tool(annotations=CHANGES)
async def publish_kma_revision(
    agent_id: Id, revision_id: Id, model_sha256: str
) -> dict[str, Any]:
    """Publish a revision exactly as previewed.

    Publish only when the KMA's owner has accepted the preview in the
    conversation. CrowdSmart refuses a candidate that changed after the
    preview, a revision that holds an answer withdrawn since, and a revision
    of a perspective that was built again since: then start a new revision.

    Args:
        agent_id: ID of a KMA you own.
        revision_id: The "revision" from start_kma_revision, for example "a2".
        model_sha256: The "model"."sha256" of the revision as previewed.
    """
    path = f"{_v2(agent_id)}/revise/{revision_id}/publish"
    return await api.call("POST", path, json={"model_sha256": model_sha256})


# ---------------------------------------------------------------------------------------
# Sources withdrawn or changed
# ---------------------------------------------------------------------------------------


@mcp.tool(annotations=READS)
async def get_kma_stale_sources(agent_id: Id) -> dict[str, Any]:
    """List the documents that a KMA's published model or frozen forecasts used and that changed since. For the KMA's owner.

    Each entry gives the "document", its "status" ("deleted", "not accepted",
    "not tagged", "changed" or "gone") with its "meaning", the passages, the
    "perspectives" whose build read it and the "frozen_forecasts" that read it.
    "not_checked" names what the report does not cover. This report changes
    nothing, and a frozen forecast never changes. To repair the perspectives
    built from such a document, use start_kma_source_repair.

    Args:
        agent_id: ID of a KMA you own.
    """
    return await api.call("GET", f"{_v2(agent_id)}/sources/stale")


@mcp.tool(annotations=CHANGES)
async def start_kma_source_repair(
    agent_id: Id, documents: list[str], reason: str, show_text: bool
) -> dict[str, Any]:
    """Start the repair of a KMA's perspectives that were built from a source since withdrawn or changed.

    A document cannot be taken out of a perspective built from it. The repair
    starts a new build of each such perspective from the domain sources as
    they are now (a changed document with its new text), with the owner's
    chosen variables and wording. Take each new build through its stages with
    get_kma_builds and decide_kma_build. At its publish stage, read the
    preview with get_kma_source_repair and publish with
    publish_kma_source_repair. Do not publish, revise or stop a repair's build
    with decide_kma_build: a publish there skips the preview check and the
    refit, and a revise or a stop ends the repair for the perspective. Until
    the repair is published, each perspective goes on forecasting, marked as
    built from a withdrawn source. Start a repair only when the KMA's owner
    decides it.

    Args:
        agent_id: ID of a KMA you own.
        documents: Document IDs from get_kma_stale_sources that a published
            perspective was built from.
        reason: Why the documents are withdrawn or changed.
        show_text: Whether the history tools can still show the text of these
            documents. If false, every history reply (versions, builds,
            refits, revisions and frozen forecasts) gives their passages by ID
            and hash only. This applies as soon as the repair starts, even if
            it is never published, and cannot be undone.
    """
    body = {"documents": documents, "reason": reason, "show_text": show_text}
    return await api.call("POST", f"{_v2(agent_id)}/sources/repair", json=body)


@mcp.tool(annotations=READS)
async def get_kma_source_repair(
    agent_id: Id, repair_id: Id | None = None
) -> dict[str, Any]:
    """Show where a KMA's source repair stands, and its next step. For the KMA's owner.

    For each perspective: its new build, its stage and "next", the step to
    take now. At the build's publish stage, "preview" shows what publishing
    changes: the variables and links added and removed, the outcome's prior and
    the open cases' forecasts before and after, and the candidate's
    "model_sha256". While an open case's "readings_waiting" is not 0, its
    "after" is not final. "complete" is true when no step is left. Without a
    repair_id, the reply lists every repair, and "text_withheld" names the
    documents whose text the history no longer shows.

    Args:
        agent_id: ID of a KMA you own.
        repair_id: The "repair" from start_kma_source_repair, for example
            "s1". Omit it to list every repair.
    """
    path = f"{_v2(agent_id)}/sources/repair"
    return await api.call("GET", path if repair_id is None else f"{path}/{repair_id}")


@mcp.tool(annotations=CHANGES)
async def publish_kma_source_repair(
    agent_id: Id, repair_id: Id, perspective: str, model_sha256: str
) -> dict[str, Any]:
    """Publish a repair's new build of one perspective, exactly as previewed.

    Publish only when the KMA's owner has accepted the preview in the
    conversation. CrowdSmart refuses a candidate that changed after the
    preview. When the domain has resolved cases, a refit starts at once to
    learn from them again. The reply names the next step: for example, publish
    that refit with publish_kma_refit when it is ready, then start and publish
    a revision to apply people's answers again. When the KMA's "counts" switch
    is on, CrowdSmart publishes that refit itself.

    Args:
        agent_id: ID of a KMA you own.
        repair_id: The repair, for example "s1".
        perspective: The perspective to publish.
        model_sha256: The "preview"."model_sha256" from get_kma_source_repair.
    """
    body = {"perspective": perspective, "model_sha256": model_sha256}
    path = f"{_v2(agent_id)}/sources/repair/{repair_id}/publish"
    return await api.call("POST", path, json=body)


@mcp.tool(annotations=CHANGES)
async def publish_kma_refit(agent_id: Id, refit_id: Id) -> dict[str, Any]:
    """Publish a refit, for example the one that a source repair started.

    A refit fits a perspective again to the domain's resolved cases. Its
    readings run on CrowdSmart's worker. get_kma_builds shows each refit's
    "stage" and queues its readings: publish when the stage is "review". Before
    that, CrowdSmart refuses and gives the stage, and the refused call queues
    the missing readings too. get_kma_build_record (kind "refit") shows the
    refit in full, but queues nothing. When the KMA's "counts" switch is on,
    CrowdSmart publishes the refits that it starts itself (after an outcome, a
    correction or a source repair), and this call is then refused with stage
    "published". These tools cannot start a refit. Publish only when the KMA's
    owner has accepted the refit in the conversation. The reply is the
    published refit, with its validation and model.

    Args:
        agent_id: ID of a KMA you own.
        refit_id: The refit, for example "r2", from get_kma_source_repair
            ("next") or get_kma_history.
    """
    return await api.call("POST", f"{_v2(agent_id)}/refit/{refit_id}/publish")
