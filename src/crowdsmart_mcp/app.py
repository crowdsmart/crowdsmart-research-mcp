"""The MCP server instance that the tool modules register their tools with."""

from mcp.server import MCPServer

INSTRUCTIONS = """\
CrowdSmart Knowledge Agents, Jams and Knowledge Model Agents. These tools act as the owner of the API key.

Knowledge Agents (KAs) answer questions from their own documents. Find them with \
list_knowledge_agents and ask with ask_knowledge_agent. In an answer, a sentence that ends \
with a citation such as [1] is evidence, checked against that passage. A sentence without a \
citation is the agent's reasoning, which is not checked. Use read_document to check a cited \
source. ask_knowledge_agent with verbose shows the evidence checks, passage counts and settings.

Jams ask Knowledge Agents (and people) to respond to prompts, then to review each other's \
responses. To have agents discuss a topic, create a few agents with create_knowledge_agent, \
each with its own perspective and documents. Then create a Jam with one prompt and their \
agent_ids (create_jam), and launch it (launch_jam). The agents work in the background. \
get_jam_results shows the progress so far; get_jam_responses shows what each agent wrote, \
with its author_id and citations. Agents answer only the first prompt of a Jam. People \
take part in the CrowdSmart app.

Some actions cannot be undone: launching a Jam sends invitation emails, and deleting a \
document is permanent. Launch a Jam only when the user asks for it.

Knowledge Model Agents (KMAs) forecast the cases of one domain (a kind of decision, with \
an outcome) through perspective models that the owner approves. list_kma_domains and \
get_kma_domain show domains and their cases; list_kmas shows your KMAs. To build one: \
create_kma on a domain, add its domain sources as documents, read each extraction as the \
KMA reads it (read_kma_extraction) and approve it (review_kma_document), tag it \
(tag_kma_document), then check_kma_build_preflight and \
start_kma_build. A build's model calls run on CrowdSmart's worker: follow it with \
get_kma_builds and make each decision it waits for with decide_kma_build, only as the \
user decides. get_kma_forecast gives a KMA's forecast for a case and why; only a forecast \
frozen before the case resolves (freeze_kma_forecast) is scored (get_kma_scoreboard). \
Freezing, resolving a case and attaching a KMA to a domain cannot be undone."""

mcp = MCPServer("crowdsmart", instructions=INSTRUCTIONS)
