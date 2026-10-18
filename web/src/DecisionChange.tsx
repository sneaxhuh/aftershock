import {
  ArrowRight,
  FileText,
  GitCompareArrows,
  ShieldCheck,
  Users,
} from "lucide-react";

type Requirement = {
  dependency_required: boolean;
  policy_required: boolean;
  dependency_id: string;
  policy_id: string;
  decisions: {
    id: string;
    name: string;
    source_id: string;
    source: string;
    text: string;
    approved_by: string;
  }[];
  prediction: { eligible: boolean; reason: string };
  version: number;
  incident: string;
  observed_verdict?: { passed: boolean; reasons: string[] } | null;
};
export type DecisionDiff = {
  available: boolean;
  reason?: string;
  changed_decision?: boolean;
  baseline?: Requirement & { verified_samples: number; snapshot_graph: string };
  current?: Requirement;
  changes?: {
    field: string;
    before: unknown;
    after: unknown;
    evidence_id: string;
  }[];
  invalidated_procedures?: {
    id: string;
    invalidated_by: string;
    revision: number;
  }[];
  evidence_ids?: string[];
};

export function DecisionChange({
  data,
  onSelect,
}: {
  data: DecisionDiff | null;
  onSelect: (ids: string[]) => void;
}) {
  if (!data?.available || !data.baseline || !data.current) return null;
  const before = data.baseline,
    now = data.current;
  const decision = now.decisions[0];
  return (
    <details className="decision-change panel" open={!!data.changed_decision}>
      <summary className="panel-heading">
        <h2>
          <GitCompareArrows size={16} />
          What changed the decision?
        </h2>
        <span
          className={`badge ${now.prediction.eligible ? "neutral" : "danger"}`}
        >
          {now.prediction.eligible
            ? "Verified baseline available"
            : "Graph blocks reuse"}
        </span>
      </summary>
      <div className="decision-comparison">
        <article>
          <span className="knowledge-label">
            Previous incident · frozen v{before.version}
          </span>
          <h3>
            <ShieldCheck size={15} />
            Fallback verified
          </h3>
          <p>
            Recommendations were{" "}
            {before.dependency_required ? "required" : "optional"}.{" "}
            {before.verified_samples} successful checkout and billing samples
            backed the recovery.
          </p>
          <code>{before.incident}</code>
          <small>{before.decisions[0]?.name}</small>
        </article>
        <article className={now.prediction.eligible ? "" : "blocked"}>
          <span className="knowledge-label">
            Current context · company v{now.version}
          </span>
          <h3>
            <ShieldCheck size={15} />
            {now.prediction.eligible
              ? "Eligible for revalidation"
              : "Fallback prohibited"}
          </h3>
          <p>{now.prediction.reason}</p>
          <code>{now.incident}</code>
          <small>
            {now.observed_verdict
              ? now.observed_verdict.passed
                ? "Current experiment passed"
                : "Current experiment rejected"
              : "Current graph check; new runtime evidence requires investigation."}
          </small>
        </article>
      </div>
      {!!data.changes?.length && (
        <div className="decision-changes">
          <span className="knowledge-label">Changed graph facts</span>
          {data.changes.map((change) => (
            <div key={change.field}>
              <code>{change.field}</code>
              <span>{JSON.stringify(change.before)}</span>
              <ArrowRight size={13} />
              <strong>{JSON.stringify(change.after)}</strong>
            </div>
          ))}
        </div>
      )}
      {decision && (
        <div className="decision-source">
          <FileText size={15} />
          <div>
            <strong>{decision.name}</strong>
            <p>{decision.text}</p>
            <span>
              <Users size={12} />
              Approved by {decision.approved_by} · {decision.source}
            </span>
          </div>
          <button
            className="btn btn-outline btn-sm"
            onClick={() =>
              onSelect([
                decision.source_id,
                decision.id,
                now.policy_id,
                now.dependency_id,
                "checkout",
                "recommendations",
              ])
            }
          >
            Follow evidence
            <ArrowRight size={13} />
          </button>
        </div>
      )}
      {!!data.invalidated_procedures?.length && (
        <div className="invalidated-procedures">
          <span className="badge warm">Procedure requires revalidation</span>
          {data.invalidated_procedures.map((procedure) => (
            <p key={procedure.id}>
              <code>{procedure.id}</code> invalidated by{" "}
              <code>{procedure.invalidated_by}</code>.
            </p>
          ))}
        </div>
      )}
      <details className="comparison-provenance">
        <summary>Inspect the captured baseline</summary>
        <code>{before.snapshot_graph}</code>
        <p>
          Compared with the current company graph. Historical probe evidence
          remains attached to its original incident.
        </p>
        <pre>
          {JSON.stringify(
            { baseline: before.decisions, current: now.decisions },
            null,
            2,
          )}
        </pre>
      </details>
    </details>
  );
}

export function CoordinationProof({
  report,
  workspace,
}: {
  report: any;
  workspace: string;
}) {
  return (
    <section className="coordination-proof panel">
      <div className="panel-heading">
        <h2>
          <Users size={15} />
          Memory isolation & handoffs
        </h2>
        <span className="badge neutral">{workspace}</span>
      </div>
      <p>
        Conversation, procedures, embeddings, incidents, and task leases are
        scoped to this workspace’s FalkorDB graphs.
      </p>
      {report?.status === "passed" ? (
        <>
          <div className="coordination-results">
            <span>
              <strong>{report.workers}</strong>simultaneous workers
            </span>
            <span>
              <strong>{report.concurrent_messages}</strong>persisted messages
            </span>
            <span>
              <strong>{report.successful_task_claims}</strong>winning task claim
            </span>
            <span>
              <strong>Passed</strong>expired-lease handoff
            </span>
          </div>
          <details>
            <summary>Inspect the real-graph check</summary>
            <p>
              {new Date(report.checked_at * 1000).toLocaleString()} ·{" "}
              {report.scope}
            </p>
            <pre>{JSON.stringify(report, null, 2)}</pre>
          </details>
        </>
      ) : (
        <p className="knowledge-empty">
          No coordination check has been recorded. Run{" "}
          <code>
            docker compose exec api python -m aftershock.check_coordination
          </code>
          .
        </p>
      )}
    </section>
  );
}
