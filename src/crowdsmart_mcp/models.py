"""Model tools: run a model version on evidence, fetch a version, fetch a run's receipt.

A model is a Bayesian belief network that CrowdSmart stores as numbered versions.
A KMA's perspective models are not model versions; get_kma_model shows them.
"""

from typing import Any

from crowdsmart_mcp import api
from crowdsmart_mcp.api import ADDS, READS, Id
from crowdsmart_mcp.app import mcp

BBM = "/api/bbm"


@mcp.tool(annotations=ADDS)
async def run_model(
    version_id: str,
    evidence: dict[str, str] | None = None,
    request_key: str | None = None,
) -> dict[str, Any]:
    """Run a model version on evidence and return the probabilities of every variable.

    CrowdSmart stores each run. The reply is the run's receipt: its "run_id",
    "posteriors" (each variable's distribution over its states, given the
    evidence), the "evidence" as recorded, the "request_key", and the version
    that ran (version_id, model_id, version_number, checksum, engine_version).
    get_model_run returns the same receipt later, to you only. Only a released
    version runs: its "status" is "released".

    To retry a run safely, for example after a timeout, send it again with the
    same request_key. CrowdSmart then returns the receipt of the first run,
    with "replayed": true, instead of adding another run.

    When a run fails, the error says why. What to do next:
    - a variable or state that the model does not have: check the names with
      get_model_version. The name of a variable is its "semantic_key";
    - evidence that is impossible under the model: change or remove a piece of
      evidence;
    - a model too large for exact inference, or a version that is not released:
      this version cannot run;
    - a request key that was already used for a different run: use a new
      request_key;
    - not found: the version does not exist, or you may not read its model. You
      can read a model that you own, a model of a community you belong to, and
      a model that came from a Jam that you can take part in;
    - a model that belongs to a Knowledge Agent's adaptive learning: these tools
      do not serve it.

    Args:
        version_id: The model version to run.
        evidence: The observed state of each observed variable, for example
            {"rain": "yes"}. Omit it for the probabilities with no evidence.
        request_key: Text of 1 to 200 characters that names this request. Give
            one when you may need to retry. Omit it to have CrowdSmart make one
            and return it.
    """
    body: dict[str, Any] = {"version_id": version_id, "evidence": evidence or {}}
    if request_key is not None:
        body["request_key"] = request_key
    return await api.call("POST", f"{BBM}/runs", json=body)


@mcp.tool(annotations=READS)
async def get_model_version(version_id: Id) -> dict[str, Any]:
    """Fetch one model version exactly as CrowdSmart stores it.

    The reply has the full "payload": the variables ("nodes") and their states,
    the links ("edges"), the probability tables ("factors") and the source
    bindings. It also has the version's "checksum", "status", "version_number"
    and "model_id". Nothing is summarized, so a copy can be checked against the
    checksum.

    Args:
        version_id: The model version, for example from a run's receipt.
    """
    return await api.call("GET", f"{BBM}/versions/{version_id}")


@mcp.tool(annotations=READS)
async def get_model_run(run_id: Id) -> dict[str, Any]:
    """Fetch the receipt of a past model run.

    The receipt has what run_model returned, except "replayed": the
    "posteriors", the "evidence", the version that ran, the run's "status",
    "created_at" and "finished_at", and any "error". Only the person who made a
    run can read its receipt. For anyone else, the run is not found.

    Args:
        run_id: The "run_id" from run_model.
    """
    return await api.call("GET", f"{BBM}/runs/{run_id}")
