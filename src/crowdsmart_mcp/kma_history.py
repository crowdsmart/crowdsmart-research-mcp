"""A KMA's past versions and records: run a published model with a receipt, and read its history.

Each publication of a KMA (a build, a refit, a revision, a rollback or a copy from
another KMA) stores a new numbered version of its definition, sealed with a hash.
CrowdSmart never changes or deletes a version. run_kma_model runs one perspective of
any version on observations and keeps a receipt. The history tools read the stored
records in full, for the KMA's owner: every version, the builds, refits and
revisions, and each frozen forecast with the inputs it was made from. The one
exception is the text of a source that the owner withheld in a source repair.
"""

from typing import Any, Literal

from crowdsmart_mcp import api
from crowdsmart_mcp.api import ADDS, READS, Id
from crowdsmart_mcp.app import mcp
from crowdsmart_mcp.kmas import DOMAINS


def _v2(agent_id: str) -> str:
    return f"/api/knowledge-agents/{agent_id}/kma/v2"


@mcp.tool(annotations=ADDS)
async def run_kma_model(
    agent_id: Id,
    perspective: str,
    observed: dict[str, str] | None = None,
    version: int | None = None,
    request_key: str | None = None,
) -> dict[str, Any]:
    """Run one perspective of a KMA's published model with chosen variables fixed.

    This is the model alone: CrowdSmart reads no case evidence, and no base rate
    or person's fact enters. It is not a case's forecast (get_kma_forecast).
    With no observations, the reply gives the model's prior.

    CrowdSmart stores each run. The reply is the run's receipt: its "run_id",
    the "request" as asked, the definition version and hash that ran
    ("definition"), the perspective's model version and hash ("model"), the
    outcome's "prior", the "posteriors" (each variable's distribution with the
    observations fixed), the "engine" and the "scope" of the run. Show the
    scope with the result. get_kma_run returns the same receipt later, to you
    only. To retry safely, for example after a timeout, send the same
    request_key: CrowdSmart then returns the first receipt, with "replayed":
    true, even if a newer version was published since.

    When a run fails, the error says why. What to do next:
    - a perspective, variable or state that the version does not have, or
      observations that are impossible under the model: check the names with
      get_kma_model;
    - a request key that was already used for a different run: use a new key;
    - no published model, or no such version: check get_kma_model.

    Args:
        agent_id: ID of a KMA you can read.
        perspective: The perspective to run, from get_kma_model.
        observed: The state of each variable to fix, for example {"rate": "high"}.
            Omit for the model's prior.
        version: The published version to run, from get_kma_model. Omit for the
            latest.
        request_key: Text of 1 to 200 characters that names this request. Give
            one when you may need to retry. Omit it to have CrowdSmart make one
            and return it.
    """
    body: dict[str, Any] = {"perspective": perspective}
    if observed is not None:
        body["observed"] = observed
    if version is not None:
        body["version"] = version
    if request_key is not None:
        body["request_key"] = request_key
    return await api.call("POST", f"{_v2(agent_id)}/runs", json=body)


@mcp.tool(annotations=READS)
async def get_kma_run(agent_id: Id, run_id: Id) -> dict[str, Any]:
    """Fetch the receipt of a past run of a KMA's model.

    The receipt has what run_kma_model returned, except "replayed". Only the
    person who made a run can read its receipt. For anyone else, the run is not
    found.

    Args:
        agent_id: The KMA that was run.
        run_id: The "run_id" from run_kma_model.
    """
    return await api.call("GET", f"{_v2(agent_id)}/runs/{run_id}")


# The history is for the KMA's owner: it holds people's answers and the text of sources.


@mcp.tool(annotations=READS)
async def get_kma_history(agent_id: Id) -> dict[str, Any]:
    """List what there is to read in a KMA's history. For the KMA's owner.

    "published" lists every version of the definition, with its hash, who
    published it and when. "perspectives" gives each perspective's model
    versions, oldest first. "builds", "refits" and "revisions" list each one by
    its ID (in the keys "build", "refit" and "revision"), with its perspective,
    who started it, when, and whether it was published. "copies" and
    "rollbacks" follow. "frozen" lists each frozen forecast and whether its
    inputs were recorded, and "switches" every change of the adaptive switches.
    Read a record with get_kma_published_version, get_kma_build_record or
    get_kma_frozen_forecast.

    Args:
        agent_id: ID of a KMA you own.
    """
    return await api.call("GET", f"{_v2(agent_id)}/history")


@mcp.tool(annotations=READS)
async def get_kma_published_version(agent_id: Id, version: int) -> dict[str, Any]:
    """Read one published version of a KMA's definition, as sealed. For the KMA's owner.

    The "definition" is the whole stored record: every perspective's network
    and probability tables, the vocabulary, the domain-source passages and the
    reader's settings. "content_sha256" is its hash. Nothing is summarized,
    so a copy can be checked against the hash. The exception is a source whose
    text the owner withheld in a source repair: its passages show by ID and
    hash only, and "text_withheld_for" names those documents. Such a reply does
    not match "content_sha256", which is the hash of the stored record with the
    text. The reply can be large.

    Args:
        agent_id: ID of a KMA you own.
        version: The version number, from get_kma_history ("published").
    """
    path = f"{_v2(agent_id)}/history/published/{version}"
    return await api.call("GET", path)


@mcp.tool(annotations=READS)
async def get_kma_build_record(
    agent_id: Id, kind: Literal["build", "refit", "revision"], record_id: Id
) -> dict[str, Any]:
    """Read a KMA's build, refit or revision in full. For the KMA's owner.

    This is the whole record that get_kma_builds and the Build page show in
    summary. A build has its proposals, link votes, elicitation tables, answers
    and model. A refit has its count tables by case, coding, validation and
    "snapshot": the resolved cases and evidence text it started from. A
    revision has the answers it applied, its tables and the rows that moved.
    Reading queues no model call: "waiting" counts the recorded calls still
    missing, and get_kma_builds queues them. A source whose text the owner
    withheld shows by ID and hash only ("text_withheld_for"). A perspective
    copied from another KMA keeps its build on that KMA. The reply can be
    large.

    Args:
        agent_id: ID of a KMA you own.
        kind: "build", "refit" or "revision".
        record_id: Its ID, from get_kma_history: for example "b1", "r1" or "a1".
    """
    path = f"{_v2(agent_id)}/history/{kind}s/{record_id}"
    return await api.call("GET", path)


@mcp.tool(annotations=READS)
async def get_kma_frozen_forecast(
    domain_id: Id, case_id: Id, agent_id: str
) -> dict[str, Any]:
    """Read a KMA's frozen forecast for a case, with the inputs it was made from. For the KMA's owner.

    "forecast" is the record as sealed. Its "inputs_snapshot" holds the
    definition, the case, the evidence passages, the base rate and people's
    facts. It also holds the reading corrections in force, and the key and hash
    of each recorded call that the forecast used. "checks" says whether the
    seals of the stored forecast and inputs hold. In "checks", "replay" says
    whether the forecast replays to the same distribution: "identical",
    "differs" or "not replayed:" with the reason (for example, a freeze made
    under an earlier method or before inputs were recorded). A frozen forecast
    never changes. If the owner withheld the text of a source in a source
    repair, its passages show by ID and hash only ("text_withheld_for"): the
    reply then does not match its seals, and "checks" is of the stored record.
    The reply can be large.

    Args:
        domain_id: The KMA's domain.
        case_id: A case that the KMA froze a forecast for.
        agent_id: ID of a KMA you own.
    """
    path = f"{DOMAINS}/{domain_id}/cases/{case_id}/frozen"
    return await api.call("GET", path, params={"agent": agent_id})
