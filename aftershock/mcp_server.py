"""Read-only, run-scoped MCP tools used by the actual investigator and verifier."""

import os
from mcp.server.fastmcp import FastMCP
from aftershock.graph import GraphStore

server = FastMCP("AFTERSHOCK graph context")
store = None
run_id = os.environ.get("MCP_RUN_ID")


def context():
    global store, run_id
    if store is None:
        store = GraphStore()
    if not run_id:
        run_id = store.active()
    if not run_id:
        raise ValueError("Select an active run or configure MCP_RUN_ID")
    run = store.get(run_id)
    return store, run


@server.tool()
def inspect_dependencies() -> dict:
    """Traverse operational dependencies and run native algo.bfs in FalkorDB."""
    graph, run = context()
    return graph.dependencies(run["company_graph"])


@server.tool()
def retrieve_evidence(query: str = "checkout recommendations timeout") -> dict:
    """Retrieve source documents using full-text plus native vector search."""
    graph, run = context()
    return graph.hybrid_evidence(run["company_graph"], query[:400])


@server.tool()
def search_incidents(
    query: str = "Orders stall when recommendations are unavailable; restore checkout without disrupting invoices",
) -> dict:
    """Retrieve episodic experience and learned procedures; recheck applicability."""
    graph, run = context()
    return {
        "episodic": graph.search_memory(),
        "procedural": graph.procedures(run["company_graph"]),
        "semantic_matches": graph.semantic_memories(query[:400]),
        "decision_diff": graph.decision_diff(run),
    }


@server.tool()
def inspect_company_context() -> dict:
    """Find service owners, teams, projects, tickets, chats and current sourced decisions."""
    graph, run = context()
    return graph.company_context(run["company_graph"])


@server.tool()
def discover_repairs() -> dict:
    """Discover the candidate set by traversing connected runbook SUGGESTS relationships."""
    graph, run = context()
    return {"candidates": graph.discover_repairs(run["company_graph"])}


@server.tool()
def explain_path(source: str = "maya", target: str = "checkout-resilience") -> dict:
    """Find a bounded directed shortest evidence path between two entity IDs."""
    graph, run = context()
    return graph.explain_path(run["company_graph"], source[:120], target[:120])


@server.tool()
def read_results() -> dict:
    """Read observed experiment evidence, eligibility checks and current company context."""
    graph, run = context()
    return {
        "experiments": graph.experiments(run),
        "current_version": run["version"],
        "company": graph.company_context(run["company_graph"]),
        "decision_diff": graph.decision_diff(run),
    }


if __name__ == "__main__":
    server.run(transport="stdio")
