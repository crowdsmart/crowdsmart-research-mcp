# crowdsmart-mcp

An MCP server for CrowdSmart. It connects an MCP client (for example Claude Desktop, Claude Code, Cursor or Hermes) to the CrowdSmart research platform (csgcip). It authenticates with your own CrowdSmart API key.

The server has 51 tools. They cover three workflows:

- Knowledge Agents that answer questions from their documents.
- Jams in which Knowledge Agents discuss a topic.
- Knowledge Model Agents (KMAs) that forecast the cases of a domain.

The server does not cover the rest of the platform. See [Scope](#scope).

## Tools

Each tool tells the client what it does to your CrowdSmart data (MCP tool annotations):

| Effect | Meaning |
|---|---|
| Reads | Changes nothing |
| Adds | Adds a record, for example a document or a Jam |
| Replaces | Replaces or deletes settings, a document, a review, a case profile value or a build |
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
| `ask_knowledge_agent` | Asks an agent a question. The answer cites the agent's documents and has a confidence score | Adds the question to the agent's query history |
| `list_documents` | Lists the documents of an agent | Reads |
| `read_document` | Returns the text of a document, for example to check a citation | Reads |
| `upload_document` | Uploads a file from this computer to your agent, then waits for its text | Adds |
| `get_document_status` | Shows whether the text of an uploaded document is ready, or why it failed | Reads |
| `add_text_document` | Adds text with its source (URL, author, date) to your agent | Adds |
| `delete_document` | Deletes a document from your agent. You cannot undo this | Replaces |
| `check_corpus_quality` | Finds damaged documents: broken lines, garbled OCR, split words and near-duplicates | Reads |

In a generative answer, a sentence that ends with a citation such as `[1]` is evidence. CrowdSmart checked it against passage 1, or shows the exact words of the passage. A sentence without a citation is the agent's own reasoning. The API calls passages "chunks".

`confidence` is a retrieval score from 0 to 1: how well the best passages match the question. A high value shows that the documents match the question. It does not show that the answer is correct.

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
| `get_kma_domain` | Shows a domain: its outcome, case fields, base-rate table, cases and KMAs | Reads |
| `create_kma_domain` | Creates a domain that you own | Adds |
| `add_kma_case` | Adds a case to a domain. You cannot remove a case | Adds |
| `set_kma_case_profile` | Sets one profile field of an open case, for example its subject | Replaces |
| `resolve_kma_case` | Records the outcome of a case. You cannot undo this | Adds |
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
| `get_kma_builds` | Shows each build: its stage, and the decision it waits for | Queues |
| `decide_kma_build` | Makes your decision at a stage of a build: variables, definitions, structure, publish, stop or revise | Replaces |
| `get_kma_forecast` | Shows the current forecast of a KMA for a case, and the readings behind it | Queues |
| `get_kma_model` | Shows the published models of a KMA: variables, links and priors | Reads |
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
9. When the case resolves, record the outcome with `resolve_kma_case`. Then compare the scores with `get_kma_scoreboard`.

A KMA reads only approved documents. When you approve the last unreviewed document of a KMA, CrowdSmart also starts its older concept and network generation, which makes model calls.

The build decisions belong to the KMA's owner. An agent that uses these tools makes a decision only when the user makes it.

A panel is three or four KMAs on one domain, one for each perspective. The panel forecast is the mean of the frozen forecasts of its members. Compare a panel with the base rate and with its best member. The mean of members that disagree always scores better than the members do on average, so this gain alone does not show skill.

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

The server covers Knowledge Agents, Jams of Knowledge Agents, and the build, forecast and scoring of Knowledge Model Agents. It does not cover other parts of the CrowdSmart platform. These include:

- Other agent types and research features
- Taking part in a Jam as a person
- Jam messages, analytics and exports
- Housekeeping, for example archiving a Jam or sending its invitations again
- KMA Jams, refits and revisions, Track and runs, and answers to a KMA's questions
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

The tests use a fake API and an in-process MCP client. Each tool module (`knowledge_agents.py`, `jams.py`, `kmas.py`) has a test file. To list the tools of the real server with the MCP Inspector, run this command once with `--protocol-era modern` and once with `--protocol-era legacy`:

```sh
npx @modelcontextprotocol/inspector --cli -e CROWDSMART_API_KEY=crc_any \
  uvx --from . crowdsmart-mcp --protocol-era modern --method tools/list
```

A tool list makes no API call, so any key value works.
