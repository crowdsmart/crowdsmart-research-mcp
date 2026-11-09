# crowdsmart-mcp

An MCP server for CrowdSmart. It connects an MCP client (for example Claude Desktop, Claude Code, Cursor or Hermes) to the CrowdSmart research platform (csgcip). It authenticates with your own CrowdSmart API key.

The server has 21 tools. They cover two workflows: Knowledge Agents that answer questions from their documents, and Jams in which Knowledge Agents discuss a topic. The server does not cover the rest of the platform. See [Scope](#scope).

## Tools

Each tool tells the client what it does to your CrowdSmart data (MCP tool annotations):

| Effect | Meaning |
|---|---|
| Reads | Changes nothing |
| Adds | Adds a record, for example a document or a Jam |
| Replaces | Replaces or deletes settings or a document |

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
      "args": ["--from", "git+https://github.com/jtkehler/crowdsmart-mcp", "crowdsmart-mcp"],
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

The server covers Knowledge Agents and Jams of Knowledge Agents. It does not cover other parts of the CrowdSmart platform. These include:

- Other agent types and research features
- Taking part in a Jam as a person
- Jam messages, analytics and exports
- Housekeeping, for example archiving a Jam or sending its invitations again

Use the CrowdSmart app for these features.

## Development

```sh
uv sync
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run basedpyright
```

The tests use a fake API and an in-process MCP client. Each tool module (`knowledge_agents.py`, `jams.py`) has a test file. To list the tools of the real server with the MCP Inspector, run this command once with `--protocol-era modern` and once with `--protocol-era legacy`:

```sh
npx @modelcontextprotocol/inspector --cli -e CROWDSMART_API_KEY=crc_any \
  uvx --from . crowdsmart-mcp --protocol-era modern --method tools/list
```

A tool list makes no API call, so any key value works.
