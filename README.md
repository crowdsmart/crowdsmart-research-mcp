# crowdsmart-mcp

An MCP server for CrowdSmart. It connects an MCP client (for example Claude Desktop, Claude Code, Cursor or Hermes) to the CrowdSmart research platform (csgcip). It authenticates with your own CrowdSmart API key.

The server has 79 tools. They cover four workflows:

- Knowledge Agents that answer questions from their documents.
- Jams in which Knowledge Agents discuss a topic.
- Knowledge Model Agents (KMAs) that forecast the cases of a domain.
- Models: run a model version on evidence and fetch the run's receipt.

The server does not cover the rest of the platform. See [Scope](#scope).

## Tools

Each tool tells the client what it does to your CrowdSmart data (MCP tool annotations):

| Effect | Meaning |
|---|---|
| Reads | Changes nothing |
| Adds | Adds a record, for example a document or a Jam |
| Replaces | Replaces or deletes settings, a document, a review, a case profile value or a build, or applies a correction that changes what counts |
| Queues | Changes nothing that you see, but can queue model calls on CrowdSmart's worker. A repeated call queues nothing new |

### Knowledge Agents

A Knowledge Agent answers questions from its own documents.

| Tool | What it does | Effect |
|---|---|---|
| `list_my_communities` | Lists your communities and your default community. A new agent or Jam goes into a community | Reads |
| `list_community_members` | Lists the members of a public community, or of a private one you belong to, with their roles and emails. Knowledge Agents shared with the community are not members | Reads |
| `list_knowledge_agents` | Lists your agents and the agents shared with you | Reads |
| `create_knowledge_agent` | Creates a private agent with no documents | Adds |
| `update_knowledge_agent` | Changes the name, headline, instructions or mode of your agent | Replaces |
| `set_knowledge_agent_visibility` | Sets who can ask your agent | Replaces |
| `ask_knowledge_agent` | Asks an agent a question. The answer cites the agent's documents and has a confidence score. With `as_of`, it answers only from the documents published on or before that day. With `verbose`, it also shows the evidence checks, passage counts and settings | Adds the question to the agent's query history |
| `list_documents` | Lists the documents of an agent | Reads |
| `read_document` | Returns the text of a document, for example to check a citation | Reads |
| `upload_document` | Uploads a file from this computer to your agent, then waits for its text | Adds |
| `get_document_status` | Shows whether the text of an uploaded document is ready, or why it failed | Reads |
| `add_text_document` | Adds text with its source (URL, author, date) to your agent | Adds |
| `list_document_dates` | Lists the publication date of each document of an agent, or why it has none | Reads |
| `set_document_publication_date` | States or withdraws the publication date of a document of your agent, with the reason | Replaces |
| `delete_document` | Deletes a document from your agent. You cannot undo this | Replaces |
| `check_corpus_quality` | Finds damaged documents: broken lines, garbled OCR, split words and near-duplicates | Reads |

In a generative answer, a sentence that ends with a citation such as `[1]` is evidence. CrowdSmart checked it against passage 1, or shows the exact words of the passage. A sentence without a citation is the agent's own reasoning. CrowdSmart does not check it against the passages. The API calls passages "chunks".

Set `verbose` to check or repeat an answer. The response then also has the check result of each sentence (`evidence`), the number of passages requested and returned (`passages`), the `chunk_id` and scores of each citation, and the settings CrowdSmart reports (`decision_trace`, `effective_config`, `interaction_id`).

`confidence` is a retrieval score from 0 to 1: how well the best passages match the question. A high value shows that the documents match the question. It does not show that the answer is correct.

To ask as of a past day, give `as_of` as `YYYY-MM-DD`. The agent then reads only its documents with a publication date on or before that day, in the text that it holds now. It does not read later or undated documents, and it does not use the model's general knowledge. A sentence without a citation is still the model's reasoning, which is not limited to that day. The answer has `notices` that say how many documents it read and left out: show them with the answer. If no document is dated on or before the day, the answer says so and no model is called. That shows a gap in the documents, not an answer to the question. `list_document_dates` shows the dates. `set_document_publication_date` states a date as a day, a month or a year. A month or a year counts as its last day.

### Jams

A Jam asks Knowledge Agents and people to respond to prompts. Then they review each other's responses. These tools run a Jam of Knowledge Agents on a topic. People take part in the CrowdSmart app.

| Tool | What it does | Effect |
|---|---|---|
| `list_jams` | Lists the active Jams that you created, take part in or can join. Your own drafts are not listed | Reads |
| `get_jam` | Shows a Jam: its status and prompts. For your own Jams, it also shows the invitees and the agents chosen in the draft | Reads |
| `create_jam` | Creates a draft Jam from a plan, with its prompts, agents and invitees. It sends nothing | Adds |
| `launch_jam` | Launches your draft. The Jam opens, its agents start and the invitees get emails. You cannot undo this | Adds |
| `add_agents_to_jam` | Adds Knowledge Agents to your active Jam | Adds |
| `get_jam_results` | Shows the results so far: participation, mean probabilities and top ideas | Reads |
| `get_jam_responses` | Shows each response: its author, probability, text and citations | Reads |

To have Knowledge Agents discuss a topic:

1. Create three to five agents with `create_knowledge_agent`. Give each agent its own perspective in `expertise_headline` and `system_prompt`.
2. Give each agent its own documents with `upload_document` or `add_text_document`.
3. Create a Jam with `create_jam`. Give one prompt and the `agent_ids` of the agents.
4. Launch the Jam with `launch_jam`.
5. Follow the progress with `get_jam_results`. Its counts show what has happened so far, not that the Jam is done: an agent that fails or abstains adds nothing.
6. Read what each agent wrote with `get_jam_responses`. Each response has its `author_id` (the agent's ID) and its citations: `[1]` in the text is citation 1. Check a cited document with `read_document`.

In the Jam, each agent responds to the prompt. Then each agent reviews the responses of the other agents. Your agents do not need to be shared to take part in your Jam.

Knowledge Agents answer only the first prompt of a Jam. For more questions, use one Jam for each question.

The tools act as the owner of your API key. Only the creator of a Jam can launch it or add agents to it. The creator is always invited to the Jam and, if invitations are sent, gets the invitation email too.

### Knowledge Model Agents

A Knowledge Model Agent (KMA) forecasts the cases of one domain. A domain is a kind of decision: an outcome with its states, and the fields that describe a case. A case is one question in the domain, with an as-of date and a resolution criterion.

A KMA is a Knowledge Agent with one or more perspective models. Each model is a Bayesian belief network that a staged build makes from the KMA's domain sources. You approve each stage. To forecast a case, each model reads the case's evidence through CrowdSmart's pinned reader. The reader runs on CrowdSmart's worker, so the results of a build or a reading come later.

| Tool | What it does | Effect |
|---|---|---|
| `list_kma_domains` | Lists every domain, with its outcome, cases and KMAs | Reads |
| `get_kma_domain` | Shows a domain: its outcome, case fields, base-rate table, cases and KMAs. Each resolved case has `resolved_at`, which a correction of its outcome names. A corrected case lists the outcomes it replaced in `resolution_history` | Reads |
| `create_kma_domain` | Creates a domain that you own | Adds |
| `add_kma_case` | Adds a case to a domain. You cannot remove a case | Adds |
| `set_kma_case_profile` | Sets one profile field of an open case, for example its subject | Replaces |
| `resolve_kma_case` | Records the outcome of a case. To fix a wrong outcome, see [KMA corrections](#kma-corrections) | Adds |
| `mark_kma_case_unscored` | Marks a case as not scored, for example when the decision came before the freeze. You cannot undo this | Adds |
| `get_kma_scoreboard` | Scores the frozen forecasts of a domain: hits, Brier score and log loss, by KMA | Reads |
| `list_kmas` | Lists your KMAs, with their domains | Reads |
| `create_kma` | Creates a KMA and attaches it to a domain | Adds |
| `enable_kma` | Makes a Knowledge Agent that you own a KMA, for example to finish a `create_kma` that stopped | Replaces |
| `attach_kma_to_domain` | Attaches your KMA to a domain. You cannot undo this here | Adds |
| `list_kma_documents` | Lists the documents of a KMA, with their extraction review and their tag | Reads |
| `read_kma_extraction` | Reads the extracted text of a document as the KMA reads it, with its digest | Reads |
| `review_kma_document` | Approves the extracted text of a document, or asks for a correction | Replaces |
| `tag_kma_document` | Tags a document as a domain source or as evidence for one case | Replaces |
| `check_kma_build_preflight` | Checks the reader, the worker, the domain and the sources before a build | Reads |
| `start_kma_build` | Starts the build of one perspective model | Adds |
| `get_kma_builds` | Shows each build: its stage, and the decision it waits for. It also shows each refit and revision with its stage | Queues |
| `decide_kma_build` | Makes your decision at a stage of a build: variables, definitions, structure, publish, stop or revise | Replaces |
| `get_kma_forecast` | Shows the current forecast of a KMA for a case, and the readings behind it | Queues |
| `get_kma_model` | Shows the published models of a KMA: variables, links and priors. With `version`, it shows them as published at that version | Reads |
| `freeze_kma_forecast` | Freezes the forecast of a KMA for a case. Only frozen forecasts are scored. You cannot undo this | Adds |
| `get_kma_switches` | Shows the adaptive switches of a KMA, and their history | Reads |
| `set_kma_switch` | Sets an adaptive switch of a KMA, with the reason | Replaces |
| `list_kma_needs` | Lists what a KMA asks people to answer, and the questions so far | Queues |
| `ask_kma_need` | Asks a need of members of the domain's cohort | Adds |
| `get_kma_cohort` | Shows the cohort of a domain: the people invited to answer questions | Reads |
| `invite_to_kma_cohort` | Invites a person to the cohort of a domain. CrowdSmart sends an email | Adds |
| `remove_from_kma_cohort` | Removes a person from the cohort of a domain | Replaces |

To build a KMA and forecast a case:

1. Find or create a domain with `list_kma_domains` or `create_kma_domain`. Add its cases with `add_kma_case`. If the domain has a `subject_field`, the models published on it read each case's evidence a whole document at a time, about the case's subject.
2. Create the KMA on the domain with `create_kma`. If it stops partway, it gives the agent's ID: finish with `enable_kma` or `attach_kma_to_domain` instead of creating another agent.
3. Add its domain sources with `add_text_document` or `upload_document`. Add the evidence for each case in the same way.
4. Read each extraction with `read_kma_extraction` and compare it with the original. This is the text that the KMA reads: headers are removed, the text is cleaned and near-duplicate passages are left out, so it can differ from `read_document`. Then approve it with `review_kma_document`, giving the digest that `read_kma_extraction` returned.
5. Tag each document with `tag_kma_document`: `domain` for a domain source, or `case` with its case ID. Give its publication date.
6. Check the KMA with `check_kma_build_preflight`. Then start the build with `start_kma_build`, with a perspective name and a brief.
7. Follow the build with `get_kma_builds`. When it waits for you, decide with `decide_kma_build`: choose the variables, check the structure, then publish. Each build lists the actions it accepts now in `next_actions`. To reject a structure, stop or revise the build. If it waits for `take_published`, another perspective was published with a different definition of one of its variables: revise or stop the build.
8. Read the forecast for a case with `get_kma_forecast`. When no readings wait, freeze it with `freeze_kma_forecast`.
9. When the case resolves, record the outcome with `resolve_kma_case`. Then compare the scores with `get_kma_scoreboard`. To fix a wrong outcome, a wrong reading, a probability or a source later, see [KMA corrections](#kma-corrections).

A KMA reads only approved documents. When you approve the last unreviewed document of a KMA, CrowdSmart also starts its older concept and network generation, which makes model calls.

The build decisions belong to the KMA's owner. An agent that uses these tools makes a decision only when the user makes it.

A panel is three or four KMAs on one domain, one for each perspective. The panel forecast is the mean of the frozen forecasts of its members. Compare a panel with the base rate and with its best member. The mean of members that disagree always scores better than the members do on average, so this gain alone does not show skill.

### KMA history and model runs

Each time a KMA publishes (a build, a refit, a revision or a rollback), CrowdSmart stores a new numbered version of its definition, sealed with a checksum. CrowdSmart does not change or delete a version.

| Tool | What it does | Effect |
|---|---|---|
| `run_kma_model` | Runs one perspective of a published version with chosen variables fixed, and returns the probabilities of every variable with a receipt. It reads no case evidence | Adds a run receipt |
| `get_kma_run` | Returns the receipt of a past run. Only the person who made the run can read it | Reads |
| `get_kma_history` | Lists the published versions, builds, refits, revisions, rollbacks and frozen forecasts of your KMA | Reads |
| `get_kma_published_version` | Returns one published version of the definition of your KMA, as sealed | Reads |
| `get_kma_build_record` | Returns a build, a refit or a revision of your KMA in full | Reads |
| `get_kma_frozen_forecast` | Returns a frozen forecast of your KMA with the inputs it was made from, and checks that it replays | Reads |

`run_kma_model` runs the model alone. It is not the forecast for a case (`get_kma_forecast`). With no fixed variables, it gives the model's prior. To retry a run safely, give the same `request_key`, as for `run_model`.

The history tools are for the KMA's owner, because the records hold people's answers and the text of sources. Each tool returns the record whole, as CrowdSmart stores it, with its checksums. A record can be hundreds of kilobytes. Some MCP clients save a large result to a file instead of putting it in the conversation. For example, Claude Code does this above 50,000 characters, and the model then reads the file. If the owner withheld the text of a source in a source repair, the history shows its passages by ID and checksum only. Such a reply does not match its checksum, which is of the stored record.

### KMA corrections

A correction changes one fact of a KMA without a new build. Each correction is a new record with its reason and the person who made it. CrowdSmart rewrites no sealed record. A correction never changes a frozen forecast: it can change only the forecast's score.

| Tool | What it does | Effect |
|---|---|---|
| `correct_kma_case_outcome` | Corrects the recorded outcome of a case | Replaces, when `preview` is false |
| `retract_kma_case_outcome` | Takes back an outcome recorded on the wrong case. The case is open again | Replaces, when `preview` is false |
| `get_kma_stale_outcomes` | Lists what the models of your KMA learned from outcomes that were corrected since | Reads |
| `set_aside_kma_reading` | Stops one reading from counting in the forecast of a case | Replaces, when `preview` is false |
| `give_kma_reading` | Gives your own reading of one passage for one variable, in place of the model's | Replaces, when `preview` is false |
| `restore_kma_reading` | Undoes a reading correction | Replaces, when `preview` is false |
| `retry_kma_failed_call` | Asks the worker to make a failed reading call again | Replaces and queues a model call, when `preview` is false |
| `get_kma_reading_corrections` | Lists the reading corrections of your KMA, and what they leave out of date | Reads |
| `state_kma_row` | States your value for one probability row, with the reason. It publishes nothing | Adds |
| `withdraw_kma_answer` | Withdraws an answer to a question of a KMA, or a row statement | Replaces |
| `start_kma_revision` | Fits a published perspective again with the answers in force, and shows the rows that move. It publishes nothing | Adds |
| `publish_kma_revision` | Publishes a revision exactly as previewed | Replaces |
| `get_kma_stale_sources` | Lists the documents that the published models or frozen forecasts used and that changed since | Reads |
| `start_kma_source_repair` | Starts a new build of each perspective that was built from a withdrawn or changed source. With `show_text` false, the history stops showing the text of the source, for good | Replaces |
| `get_kma_source_repair` | Shows where a source repair stands, its next step and its preview | Reads |
| `publish_kma_source_repair` | Publishes the new build of one perspective, exactly as previewed | Replaces |
| `publish_kma_refit` | Publishes a refit, for example the one that a source repair started | Replaces |

A correction tool with `preview` returns a report of what the correction changes and writes nothing. Set `preview` to false only when the owner accepts the report. If the fact changed after the report, CrowdSmart refuses the correction and gives the reason: read the fact again.

To correct:

- **An outcome.** `get_kma_domain` gives the `resolved_at` of each resolved case. Give it as `replaces` to `correct_kma_case_outcome` or `retract_kma_case_outcome`. The replaced outcome stays in the case's `resolution_history`.
- **A reading.** `get_kma_forecast` gives the `call` of each reading, and the `failed_calls`. Set a reading aside by its call, or give your own reading of the passage with a quote from it.
- **A probability or an answer.** State a row with `state_kma_row`, or withdraw an answer with `withdraw_kma_answer`. Then start a revision with `start_kma_revision`, check the rows that move, and publish it with `publish_kma_revision` and the `model.sha256` of the revision.
- **A source.** A document cannot be taken out of a perspective that was built from it. `start_kma_source_repair` builds each such perspective again from the domain sources as they are now. Take each build through its stages with `get_kma_builds` and `decide_kma_build`. Then publish it with `publish_kma_source_repair` and the `model_sha256` of its preview. Do not publish, revise or stop a repair's build with `decide_kma_build`. If the domain has resolved cases, a refit starts. `get_kma_builds` shows when it is ready: then publish it with `publish_kma_refit`. When the KMA's `counts` switch is on, CrowdSmart publishes it itself. `get_kma_source_repair` gives the next step each time. These tools cannot start a refit.

### Models

A model is a Bayesian belief network that CrowdSmart stores as numbered versions. A KMA's perspective models are not model versions: `get_kma_model` shows them.

| Tool | What it does | Effect |
|---|---|---|
| `run_model` | Runs a model version on evidence and returns the probabilities of every variable, with a `run_id` | Adds a run receipt |
| `get_model_version` | Returns a model version exactly as stored: variables, states, links, probability tables, source bindings and checksum | Reads |
| `get_model_run` | Returns the receipt of a past run. Only the person who made the run can read it | Reads |

`evidence` maps each observed variable to its state, for example `{"rain": "yes"}`. The receipt gives the probabilities in `posteriors`. Only a released version runs: its `status` is `released`. To retry a run safely, for example after a timeout, give the same `request_key`. CrowdSmart then returns the first run instead of adding another. If you do not give a `request_key`, CrowdSmart makes one and returns it. Give a `request_key` on the first call if you may need to retry.

You can read and run these models: a model that you own, a model of a community you belong to, and a model that came from a Jam that you can take part in. These tools do not serve a model that belongs to the adaptive learning of a Knowledge Agent.

## Requirements

- [uv](https://docs.astral.sh/uv/). `uvx` gets Python 3.13 and the dependencies when necessary.
- [Git](https://git-scm.com/). uv uses it to get the server from GitHub.
- A CrowdSmart account and an API key.

## Get an API key

1. Sign in to CrowdSmart and open the **User Dashboard**.
2. In the **API Key** card, generate a key. The key starts with `crc_`.
3. Copy the key. CrowdSmart shows it only once.

A new key replaces your old key.

## Add the server to your MCP client

Add this entry to the MCP configuration of your client. For Claude Desktop, the file is `claude_desktop_config.json`.

```json
{
  "mcpServers": {
    "crowdsmart": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/crowdsmart/crowdsmart-research-mcp", "crowdsmart-mcp"],
      "env": { "CROWDSMART_API_KEY": "crc_your_key" }
    }
  }
}
```

To use a local checkout, replace the `--from` value with the path of the checkout.

## Environment variables

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `CROWDSMART_API_KEY` | Yes | | Your CrowdSmart API key. The server sends it only to the API URL, as a bearer token in the `Authorization` header |
| `CROWDSMART_API_URL` | No | `https://csgcip.onrender.com` | The CrowdSmart API. The server sends your key to this URL, so set it only to a deployment that you trust |

If `CROWDSMART_API_KEY` is not set, the server stops at startup and writes the reason to stderr.

## Scope

The server covers Knowledge Agents, Jams of Knowledge Agents, the build, forecast, scoring, history and corrections of Knowledge Model Agents, and runs of model versions. It does not cover other parts of the CrowdSmart platform. These include:

- Other agent types and research features
- Taking part in a Jam as a person
- Jam messages, analytics and exports
- Housekeeping, for example archiving a Jam or sending its invitations again
- KMA Jams, starting a refit, rollbacks, Track and the scheduled runs of a domain, and answering a KMA's questions
- Schedules: a domain's jobs that collect evidence, freeze and resolve cases at set times. Your MCP client can do these steps with the tools above

Use the CrowdSmart app for these features.

## Development

```sh
uv sync
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run basedpyright
```

The tests use a fake API and an in-process MCP client. Each tool module (`knowledge_agents.py`, `jams.py`, `kmas.py`, `kma_history.py`, `kma_corrections.py`, `models.py`) has a test file. To list the tools of the real server with the MCP Inspector, run this command once with `--protocol-era modern` and once with `--protocol-era legacy`:

```sh
npx @modelcontextprotocol/inspector --cli -e CROWDSMART_API_KEY=crc_any \
  uvx --from . crowdsmart-mcp --protocol-era modern --method tools/list
```

A tool list makes no API call, so any key value works.
