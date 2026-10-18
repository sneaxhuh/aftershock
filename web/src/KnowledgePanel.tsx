import {
  BookOpen,
  Braces,
  Check,
  ChevronRight,
  Database,
  FileText,
  GitBranch,
  Network,
  ShieldCheck,
  Users,
} from "lucide-react";

export type CompanyContext = {
  owners: {
    id: string;
    name: string;
    service: string;
    team: string;
    evidence_id: string;
  }[];
  projects: { id: string; name: string; team: string }[];
  decisions: {
    id: string;
    name: string;
    required: boolean;
    approved_by: string;
    source_id: string;
    text: string;
    source: string;
  }[];
  sources: {
    id: string;
    name: string;
    kind: string;
    source: string;
    text: string;
    current_decision_source: boolean;
  }[];
  candidates: {
    action: string;
    name: string;
    source_id: string;
    target: string;
    prediction: { eligible: boolean; reason: string };
  }[];
  procedures: {
    id: string;
    action: string;
    text: string;
    confirmed_runs: number;
    applicable: boolean;
    current_reason: string;
    revision: number;
    evidence_ids: string[];
  }[];
  owner_path: { nodes: string[]; edges: string[]; algorithm: string };
  insights: { query: string; plan: string; features: string[] };
  deployments: {
    id: string;
    name: string;
    checkout_version: number;
    schema_version: number;
    migration: { id: string; name: string; backward_compatible: boolean };
    owner: { id: string; name: string };
    project: { id: string; name: string };
    document: { id: string; text: string; source: string };
    evidence_ids: string[];
    query: string;
  }[];
};

export function KnowledgePanel({
  context,
  onSelect,
}: {
  context: CompanyContext | null;
  onSelect: (ids: string[]) => void;
}) {
  if (!context) return null;
  const owner = context.owners.find((owner) => owner.service === "checkout");
  const decision = context.decisions[0];
  return (
    <section className="knowledge-panel panel" id="company-context">
      <div className="panel-heading">
        <h2>
          <Network size={16} /> Company context{" "}
          <span className="count">{context.sources.length} sources</span>
        </h2>
        <span className="mono">Available to agents via MCP</span>
      </div>
      <div className="knowledge-summary">
        <div>
          <span className="knowledge-label">
            <Users size={13} /> Service owner
          </span>
          <strong>{owner?.name || "Ownership missing"}</strong>
          <p>{owner?.team || "No team relationship"}</p>
        </div>
        <div>
          <span className="knowledge-label">
            <GitBranch size={13} /> Project
          </span>
          <strong>{context.projects[0]?.name || "No connected project"}</strong>
          <p>{context.candidates.length} runbook-connected repair hypotheses</p>
        </div>
        <div>
          <span className="knowledge-label">
            <ShieldCheck size={13} /> Current decision
          </span>
          <strong>{decision?.name || "Approval evidence missing"}</strong>
          <p>
            {decision
              ? `Approved by ${decision.approved_by}`
              : "Repairs requiring approval will be blocked."}
          </p>
        </div>
        <div>
          <span className="knowledge-label">
            <Database size={13} /> Learned experience
          </span>
          <strong>
            {context.procedures.length} verified procedure
            {context.procedures.length === 1 ? "" : "s"}
          </strong>
          <p>
            {context.procedures.filter((p) => p.applicable).length} applicable
            under current requirements
          </p>
        </div>
      </div>
      <div className="knowledge-details">
        <details>
          <summary>
            <GitBranch size={14} />
            Deployment & migration provenance
            <span>{context.deployments?.length || 0} active release</span>
          </summary>
          {context.deployments?.map((deployment) => (
            <article className="deployment-record" key={deployment.id}>
              <div className="deployment-heading">
                <strong>{deployment.name}</strong>
                <span
                  className={`badge ${deployment.migration.backward_compatible ? "neutral" : "warm"}`}
                >
                  {deployment.migration.backward_compatible
                    ? "Backward compatible"
                    : "Incompatible with checkout v1"}
                </span>
              </div>
              <div className="deployment-chain">
                <code>{deployment.id}</code>
                <ChevronRight size={13} />
                <code>{deployment.migration.id}</code>
                <ChevronRight size={13} />
                <code>schema v{deployment.schema_version}</code>
              </div>
              <p>{deployment.document.text}</p>
              <small>
                Approved by {deployment.owner.name} · {deployment.project.name}
              </small>
              <button
                className="btn btn-outline btn-sm"
                onClick={() => onSelect(deployment.evidence_ids)}
              >
                Follow deployment evidence
                <ChevronRight size={13} />
              </button>
              <details>
                <summary>Source and Cypher</summary>
                <code>{deployment.document.source}</code>
                <pre>{deployment.query}</pre>
              </details>
            </article>
          ))}
        </details>
        <details>
          <summary>
            <BookOpen size={14} /> Inspect tickets, chats & decision sources{" "}
            <span>{context.sources.length} records</span>
          </summary>
          <div className="source-grid">
            {context.sources.map((source) => (
              <article key={source.id} className="source-card">
                <div>
                  <span className="badge neutral">{source.kind}</span>
                  {source.current_decision_source && (
                    <span className="badge success">
                      <Check size={10} />
                      Current decision source
                    </span>
                  )}
                </div>
                <h3>{source.name}</h3>
                <p>{source.text}</p>
                <button onClick={() => onSelect([source.id])}>
                  <FileText size={12} />
                  {source.source}
                </button>
              </article>
            ))}
          </div>
        </details>
        <details>
          <summary>
            <Braces size={14} /> Follow the owner → decision → project path{" "}
            <span>shortestPath</span>
          </summary>
          <button
            className="path-trail"
            onClick={() =>
              onSelect([
                ...context.owner_path.nodes,
                ...context.owner_path.edges,
              ])
            }
          >
            {context.owner_path.nodes.map((node, index) => (
              <span key={node}>
                {index > 0 && <ChevronRight size={12} />}
                <code>{node}</code>
              </span>
            ))}
          </button>
          <pre>
            {context.insights?.query}
            {"\n\n"}
            {context.insights?.plan}
          </pre>
        </details>
      </div>
    </section>
  );
}

export function ProcedureMemory({
  procedures,
}: {
  procedures: CompanyContext["procedures"];
}) {
  return (
    <section className="procedure-memory">
      <div className="section-heading">
        <h2>
          <ShieldCheck size={16} /> Learned procedures
        </h2>
        <span className="mono">Revalidated against current requirements</span>
      </div>
      {procedures.length ? (
        procedures.map((procedure) => (
          <article
            key={procedure.id}
            className={`procedure-card ${procedure.applicable ? "applicable" : "invalidated"}`}
          >
            <div>
              <span
                className={`badge ${procedure.applicable ? "success" : "danger"}`}
              >
                {procedure.applicable
                  ? "Applicable now"
                  : "Revalidation required"}
              </span>
              <span className="mono">
                v{procedure.revision} · {procedure.confirmed_runs} verified
                recoveries
              </span>
            </div>
            <h3>{procedure.action.replaceAll("_", " ")}</h3>
            <p>{procedure.text}</p>
            <strong>{procedure.current_reason}</strong>
          </article>
        ))
      ) : (
        <p className="knowledge-empty">
          Verified recoveries create reusable procedures with explicit
          preconditions. None have been learned yet.
        </p>
      )}
    </section>
  );
}

export function ConversationMemory({
  messages,
}: {
  messages: {
    sequence: number;
    role: string;
    kind: string;
    incident: number;
    at: number;
    content: unknown;
  }[];
}) {
  return (
    <section className="conversation-memory">
      <div className="section-heading">
        <h2>
          <FileText size={16} /> Persistent agent dialogue
        </h2>
        <span className="mono">Latest {messages.length} public messages</span>
      </div>
      {messages.length ? (
        messages.map((message) => (
          <details key={message.sequence} className="message-record">
            <summary>
              <span className="badge neutral">{message.role}</span>
              <strong>{message.kind.replaceAll("_", " ")}</strong>
              <span className="mono">
                INCIDENT {message.incident} ·{" "}
                {new Date(message.at * 1000).toLocaleTimeString()}
              </span>
            </summary>
            <pre>{JSON.stringify(message.content, null, 2)}</pre>
          </details>
        ))
      ) : (
        <p className="knowledge-empty">
          Agent messages and MCP tool results will be persisted here. Private
          model thought fields are excluded.
        </p>
      )}
    </section>
  );
}
