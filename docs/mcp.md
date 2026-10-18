# Graph tools over MCP

AFTERSHOCK uses the official Python MCP SDK with a real stdio server and client session. The controller starts a run-scoped server, initializes a session, discovers schemas using `list_tools`, presents those schemas to Gemini, and dispatches selected graph tools through `call_tool`.

| Tool | Context returned |
| --- | --- |
| `inspect_dependencies` | Multi-hop dependency paths and native `algo.bfs` results. |
| `retrieve_evidence(query)` | Full-text and vector document matches, source references, retrieval availability. |
| `search_incidents(query)` | Episodic outcomes, revalidated procedures, semantic memory matches. |
| `inspect_company_context` | Owners, teams, projects, current approved decisions, source records. |
| `discover_repairs` | Enabled repairs reachable through runbook suggestions, predictions, learned applicability. |
| `explain_path(source, target)` | A bounded directed native shortest evidence path. |
| `read_results` | Persisted experiments, observed probes, and current company context. |

The investigator must retrieve all six investigation tools before submitting its proposal. The verifier independently reads results. The coordinator and supervisor execute validated operations in deterministic code. MCP tool results and public model replies are stored in FalkorDB and visible in incident memory.

For a compatible local MCP client, launch the server inside the running API container:

```json
{
  "mcpServers": {
    "aftershock": {
      "command": "docker",
      "args": ["compose", "exec", "-T", "api", "python", "-m", "aftershock.mcp_server"]
    }
  }
}
```

Run the command with this repository as its working directory. It selects the active company by default. To inspect a specific persisted run, insert `-e`, `MCP_RUN_ID=<run-id>` after `-T`. The tools accept entity IDs and search text, never arbitrary graph names, Cypher, or shell commands. This local read interface relies on access to the Docker host; it is not a remotely authenticated tenant boundary.

For Harbor, also pass `-e AFTERSHOCK_TENANT=harbor` before `api`. The controller does this automatically for its agents. The selected run must exist in that tenant's memory graph; a peer run ID is rejected. `search_incidents` and `read_results` also include the graph-backed decision comparison. Company context includes deployment/migration provenance.
