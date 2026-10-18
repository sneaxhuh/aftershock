# A repair is a hypothesis: building AFTERSHOCK with FalkorDB

An alert tells us where a symptom appeared. A repair needs more context: what depends on the target, which workflows those systems support, which requirements changed, and what happened when we last tried a similar action.

AFTERSHOCK models these connections in FalkorDB. Checkout depends on recommendations, inventory, and shared data. Billing also depends on shared data. The current database schema supports checkout v2, while v1 requires a different schema. A policy determines whether recommendations may be bypassed.

That model makes three superficially reasonable fixes distinguishable. Rollback violates schema compatibility. A shared-data restart risks another workflow. Graceful fallback is eligible only while recommendations remain optional.

The model also determines which hypotheses exist. The investigator discovers repairs by following a service's connected runbooks through `SUGGESTS` and `TARGETS` relationships. The executors remain bounded application code, but the proposal's candidate set comes from graph connectivity. Removing a suggestion removes that repair from discovery.

Company context provides authority as well as topology. People belong to teams, teams lead projects, and projects include services. A current owner-approved decision cites its source document and establishes the recommendations policy. An older chat cannot override a superseding decision. A native shortest path makes the owner → decision → project connection visible, while `algo.bfs` provides the operational dependency frontier.

Deployment provenance explains how the compatibility constraint arose. The incident ticket follows DEP-481, whose approved release applied a migration producing schema v2. The deployment belongs to the checkout resilience project and cites its release source. The investigator follows this chain, and the rollback verifier requires the deployment/migration path to agree with data-service schema support. Restarting an old checkout process cannot reverse that database migration.

These are actual agent tools over MCP, using stdio transport and runtime schema discovery. Gemini selects the read tools; the controller validates its proposed action set against the graph. Full-text retrieval and native vector indexes find source documents and prior experience. Embeddings come from a real configurable Gemini embedding model, are cached in FalkorDB, and never stand in for execution evidence. A provider failure is disclosed as lexical-only retrieval.

The graph cannot prove the services will behave as predicted. We therefore freeze a SQLite backup and configuration, copy the incident graph with GRAPH.COPY, and restore independent service processes for each candidate. Continuous HTTP probes measure checkout and billing before, during, and after the intervention. Restarting data actually changes its PID and produces billing failures. Rollback actually executes checkout v1 and returns a schema error.

The verifier separates predicted impact from observed impact. Graph rules gate eligibility; measured workflow probes establish recovery. A candidate must satisfy both. An interruption that happens during a restart still matters even if the service is healthy afterward.

The coordination graph holds task leases, completed handoffs, experiment records, observations, ordered events, and public model/tool dialogue. Roles do not depend on an uninterrupted chat session. The next investigator retrieves prior incidents and revalidated procedures through full-text and semantic search.

After a verified main-environment recovery, the system distills a reusable procedure linked to its successful outcome and semantic precondition. Distinct incident outcomes provide confirmation counts. Remembered procedures influence investigation ordering, while isolated experiments and current graph checks remain mandatory. Selection and rejection decisions link back to the exact experiment evidence.

The second demonstration changes one requirement: recommendations become mandatory. The previous repair is useful experience, but it is no longer eligible. The new sourced decision supersedes the earlier approval and invalidates the learned procedure. The system explains the relevant dependency, policy, and owner approval facts, leaves the incident unresolved, and records an internal escalation assigned through the service ownership relationship. Remembering and obeying current context are different capabilities; a useful agent needs both.

The decision-change view makes this visible side by side. It compares the earlier recovery's frozen graph with today's company graph, showing the changed dependency, policy, approval source, and invalidated procedure. It distinguishes a graph prohibition from a rejection backed by a newly completed experiment. Old experiments become stale when requirements change and cannot authorize application.

Two synthetic company workspaces keep their conversation, procedural, episodic, semantic, and coordination state in separate FalkorDB graphs. Signed workspace sessions bind HTTP requests, and MCP inherits the same trusted tenant scope. A snapshot-switched sandbox pool preserves each company's executable state while allowing only one investigation at a time. A focused real-graph check exercises eight simultaneous workers, exclusive claims, expired leases, and persisted handoffs; it demonstrates correctness rather than claiming production-scale throughput.

The implementation intentionally uses two small synthetic company workspaces and bounded interventions. It is not a general causal inference engine or autonomous production remediation platform. It is a reproducible demonstration of connected context changing what an agent is allowed to do, backed by actual execution evidence.
