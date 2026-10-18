import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createRoot } from "react-dom/client";
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  MarkerType,
  type NodeProps,
} from "@xyflow/react";
import {
  Activity,
  ArrowDownLeft,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Boxes,
  Braces,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  Command,
  Database,
  ExternalLink,
  FileText,
  GitBranch,
  Layers3,
  Loader2,
  Maximize2,
  Network,
  Play,
  Radio,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Terminal,
  Workflow,
  X,
  Zap,
  Users,
} from "lucide-react";
import "@xyflow/react/dist/style.css";
import "./style.css";
import {
  KnowledgePanel,
  ProcedureMemory,
  ConversationMemory,
  type CompanyContext,
} from "./KnowledgePanel";
import {
  DecisionChange,
  CoordinationProof,
  type DecisionDiff,
} from "./DecisionChange";

type Sample = {
  at: number;
  checkout: {
    ok: boolean;
    status: number;
    duration_ms: number;
    body: Record<string, unknown>;
  };
  billing: {
    ok: boolean;
    status: number;
    duration_ms: number;
    body: Record<string, unknown>;
  };
};
type Prediction = {
  eligible: boolean;
  reason: string;
  evidence_ids: string[];
  affected_customer_groups: number;
  query: string;
};
type Experiment = {
  action: string;
  title: string;
  graph: string;
  version: number;
  status: string;
  prediction: Prediction;
  observations: Sample[];
  verdict: null | {
    passed: boolean;
    reasons: string[];
    billing_failures: number;
    checkout_failures: number;
    evidence_ids: string[];
  };
  duration_ms?: number;
  checksum: string;
  discrepancy?: boolean;
  processes_before?: Record<string, { pid: number }>;
  processes_after?: Record<string, { pid: number }>;
};
type Run = {
  id: string;
  name: string;
  status: string;
  version: number;
  incident: number;
  fault: boolean;
  required: boolean;
  recommendation: string | null;
  experiments: Experiment[];
  error?: string;
  report?: string;
  model_calls: number;
  snapshot_version?: number;
  candidates?: { action: string }[];
  escalation?: { owner: { name: string; team: string }; status: string };
};
type Event = {
  sequence: number;
  at: number;
  role: string;
  title: string;
  detail: string;
  evidence_ids?: string[];
};
type Graph = {
  name: string;
  nodes: { id: string; labels: string[]; properties: Record<string, any> }[];
  edges: {
    source: string;
    target: string;
    type: string;
    properties: Record<string, any>;
  }[];
};
const actions = [
  {
    id: "rollback_checkout",
    name: "Roll back checkout",
    tag: "ROLLBACK",
    icon: RotateCcw,
    description: "Restore checkout v1 and test schema compatibility.",
  },
  {
    id: "restart_data",
    name: "Restart shared data",
    tag: "RESTART",
    icon: Database,
    description: "Restart the shared dependency. Watch both workflows.",
  },
  {
    id: "enable_fallback",
    name: "Enable graceful fallback",
    tag: "FALLBACK",
    icon: GitBranch,
    description: "Bypass optional recommendations and preserve checkout.",
  },
];
async function api(path: string, body?: unknown) {
  const response = await fetch(
    "/api" + path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      data.detail || data.error || "The request could not be completed.",
    );
  return data;
}
const time = (value: number) =>
  new Date(value * 1000).toLocaleTimeString("en-GB", { hour12: false });

function ServiceNode({ data }: NodeProps) {
  const d = data as any;
  const Icon =
    d.kind === "Schema"
      ? Braces
      : d.kind === "Person"
        ? Users
        : d.kind === "Document"
          ? FileText
          : d.kind === "Workflow"
            ? Workflow
            : d.id === "data"
              ? Database
              : d.kind === "Policy" || d.kind === "Decision"
                ? ShieldCheck
                : d.kind === "Project"
                  ? GitBranch
                  : d.kind === "Team"
                    ? Users
                    : Boxes;
  return (
    <div
      className={`service-node ${d.health || ""} ${d.selected ? "evidence-selected" : ""}`}
      title={d.label}
    >
      <Handle type="target" position={Position.Left} />
      <div className="node-icon">
        <Icon size={16} />
      </div>
      <div>
        <span className="node-kind">
          {d.kind === "Service" ? "SERVICE" : d.kind.toUpperCase()}
        </span>
        <strong>{d.label}</strong>
        <span className="node-caption">{d.caption}</span>
      </div>
      <span
        className={`status-dot ${d.health === "failed" ? "red" : d.health === "changed" ? "orange" : "green"}`}
      />
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
const nodeTypes = { service: ServiceNode };

function App() {
  const [config, setConfig] = useState<any>(null),
    [run, setRun] = useState<Run | null>(null),
    [graph, setGraph] = useState<Graph | null>(null);
  const [events, setEvents] = useState<Event[]>([]),
    [samples, setSamples] = useState<Sample[]>([]),
    [branch, setBranch] = useState("company");
  const [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [drawer, setDrawer] = useState<Experiment | null>(null),
    [tab, setTab] = useState("command");
  const [expanded, setExpanded] = useState(false),
    [selected, setSelected] = useState<string[]>([]),
    [memory, setMemory] = useState<any[]>([]),
    [help, setHelp] = useState(false);
  const [connected, setConnected] = useState(false),
    [lastUpdate, setLastUpdate] = useState<number | null>(null);
  const [compact, setCompact] = useState(window.innerWidth < 650);
  const [company, setCompany] = useState<CompanyContext | null>(null);
  const [conversation, setConversation] = useState<any[]>([]);
  const [graphWide, setGraphWide] = useState(false);
  const [pendingPolicy, setPendingPolicy] = useState<boolean | null>(null);
  const [contextFocus, setContextFocus] = useState<string[] | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [decisionDiff, setDecisionDiff] = useState<DecisionDiff | null>(null);
  const [coordination, setCoordination] = useState<any>(null);
  const boundTenant = useRef<string | null>(null);
  const acceptConfig = useCallback((value: any) => {
    if (boundTenant.current && boundTenant.current !== value.tenant_id) {
      window.location.reload();
      return false;
    }
    boundTenant.current = value.tenant_id;
    setConfig(value);
    return true;
  }, []);
  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setDrawer(null);
        setHelp(false);
      }
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);
  useEffect(() => {
    const resize = () => setCompact(window.innerWidth < 650);
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);
  const refresh = useCallback(async (id: string) => {
    const value = await api("/runs/" + id);
    setRun(value);
    return value;
  }, []);
  useEffect(() => {
    api("/config")
      .then(async (c) => {
        if (!acceptConfig(c)) return;
        if (c.active_run) await refresh(c.active_run);
      })
      .catch((e) => setError(e.message));
  }, [refresh, acceptConfig]);
  useEffect(() => {
    const timer = setInterval(
      () =>
        api("/config")
          .then(acceptConfig)
          .catch(() => {}),
      5000,
    );
    return () => clearInterval(timer);
  }, [acceptConfig]);
  useEffect(() => {
    if (!run?.id) return;
    const stream = new EventSource(`/api/runs/${run.id}/events`);
    stream.onopen = () => setConnected(true);
    stream.onerror = () => setConnected(false);
    stream.onmessage = (event) => {
      const item: Event = JSON.parse(event.data);
      setEvents((old) =>
        old.some((e) => e.sequence === item.sequence) ? old : [...old, item],
      );
      setLastUpdate(Date.now());
    };
    return () => {
      stream.close();
      setConnected(false);
    };
  }, [run?.id]);
  useEffect(() => {
    if (!run?.id) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const value = await refresh(run.id);
        if (
          !cancelled &&
          value.status !== "archived" &&
          config?.can_control !== false
        ) {
          const observation = await api(`/runs/${run.id}/observe`);
          if (!cancelled) setSamples((old) => [...old.slice(-39), observation]);
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    };
    tick();
    const timer = setInterval(tick, 2000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [run?.id, refresh, config?.can_control]);
  useEffect(() => {
    if (!run?.id) return;
    let cancelled = false;
    setGraphLoading(true);
    api(`/runs/${run.id}/graph?branch=${branch}`)
      .then((value) => {
        if (!cancelled) setGraph(value);
      })
      .catch((e) => {
        if (cancelled) return;
        if (branch !== "company") setBranch("company");
        else setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setGraphLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [run?.id, run?.version, run?.status, branch]);
  useEffect(() => {
    if (run?.id)
      api(`/runs/${run.id}/context`)
        .then(setCompany)
        .catch((e) => setError(e.message));
    else setCompany(null);
  }, [run?.id, run?.version, run?.status]);
  useEffect(() => {
    if (run?.id)
      api(`/runs/${run.id}/decision-diff`)
        .then(setDecisionDiff)
        .catch((e) => setError(e.message));
    else setDecisionDiff(null);
  }, [run?.id, run?.version, run?.status]);
  useEffect(() => {
    if (tab === "memory")
      api("/coordination-check")
        .then(setCoordination)
        .catch((e) => setError(e.message));
  }, [tab]);
  useEffect(() => {
    if (tab === "memory" && run)
      api(`/runs/${run.id}/memory`)
        .then(setMemory)
        .catch((e) => setError(e.message));
  }, [tab, run?.status, run?.id]);
  useEffect(() => {
    if (tab === "memory" && run)
      api(`/runs/${run.id}/conversation`)
        .then(setConversation)
        .catch((e) => setError(e.message));
  }, [tab, run?.status, run?.id]);
  async function command(name: string, task: () => Promise<any>) {
    setBusy(name);
    setError("");
    try {
      await task();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function initialize() {
    setEvents([]);
    setSamples([]);
    setBranch("company");
    setContextFocus(null);
    setSelected([]);
    setExpanded(false);
    setRun(
      await api("/runs", {
        name: config?.workspace_name || "Northstar Commerce",
      }),
    );
  }
  async function act(path: string, body: unknown = {}) {
    if (!run) return;
    const result = await api(`/runs/${run.id}/${path}`, body);
    if (result.id) setRun(result);
  }
  async function switchWorkspace(tenant: string) {
    await command("workspace", async () => {
      await api(`/workspaces/${tenant}/activate`, {});
      window.location.reload();
    });
  }
  const latest = samples.at(-1),
    running = run?.status === "investigating",
    ready = run?.status === "ready",
    recovered = run?.status === "resolved";
  const displayedActions = company
    ? company.candidates
        .map((candidate) =>
          actions.find((action) => action.id === candidate.action),
        )
        .filter((action): action is (typeof actions)[number] => !!action)
    : actions;
  const flow = useMemo(() => {
    if (!graph) return { nodes: [], edges: [] };
    const experiment = run?.experiments.find((e) => e.action === branch);
    const currentProbe =
      branch === "company" ? latest : experiment?.observations.at(-1);
    const fallbackActive =
      branch === "company"
        ? recovered
        : branch === "enable_fallback" && !!experiment?.verdict?.passed;
    const focus = new Set(contextFocus || []);
    if (contextFocus) {
      const nodeIds = new Set(
        graph.nodes.filter((n) => focus.has(n.id)).map((n) => n.id),
      );
      graph.edges.forEach((edge) => {
        if (
          focus.has(edge.properties.id) ||
          (nodeIds.size === 1 &&
            (nodeIds.has(edge.source) || nodeIds.has(edge.target)))
        ) {
          focus.add(edge.source);
          focus.add(edge.target);
        }
      });
    }
    const order = Array.from(focus);
    const visible = graph.nodes
      .filter(
        (n) =>
          (expanded || n.labels[0] === "Service") &&
          (!contextFocus || focus.has(n.id)),
      )
      .sort((a, b) =>
        contextFocus ? order.indexOf(a.id) - order.indexOf(b.id) : 0,
      );
    const ids = new Set(visible.map((n) => n.id));
    const positions: Record<string, { x: number; y: number }> = {
      checkout: { x: 30, y: 80 },
      recommendations: { x: 340, y: 0 },
      inventory: { x: 340, y: 155 },
      billing: { x: 30, y: 310 },
      data: { x: 650, y: 280 },
    };
    return {
      nodes: visible.map((n, index) => {
        let health = "";
        if (n.id === "recommendations" && run?.fault) health = "failed";
        if (n.id === "checkout" && currentProbe && !currentProbe.checkout.ok)
          health = "failed";
        if (n.id === "checkout" && fallbackActive) health = "changed";
        return {
          id: n.id,
          type: "service",
          position: contextFocus
            ? { x: (index % 3) * 310, y: Math.floor(index / 3) * 175 }
            : expanded
              ? { x: n.properties.x, y: n.properties.y }
              : positions[n.id] || { x: 0, y: 0 },
          data: {
            id: n.id,
            label: n.properties.name,
            kind: n.labels[0],
            health,
            selected: selected.includes(n.id),
            caption:
              n.id === "checkout"
                ? `v${n.properties.version || 2} · ${fallbackActive ? "fallback active" : "HTTP service"}`
                : n.id === "data"
                  ? "SQLite · schema v2"
                  : n.labels[0] === "Service"
                    ? "HTTP service"
                    : n.properties.required
                      ? "required"
                      : "context",
          },
        };
      }),
      edges: graph.edges
        .filter((e) => ids.has(e.source) && ids.has(e.target))
        .map((e) => {
          const high = selected.includes(e.properties.id);
          const fault = e.target === "recommendations" && run?.fault;
          return {
            id: e.properties.id,
            source: e.source,
            target: e.target,
            label:
              e.type === "DEPENDS_ON"
                ? e.properties.required
                  ? "required"
                  : "optional"
                : e.type.toLowerCase().replaceAll("_", " "),
            animated: !!fault,
            style: {
              stroke: high ? "#d7b575" : fault ? "#d77d7d" : "#58616b",
              strokeWidth: high ? 3 : 1.5,
              strokeDasharray:
                e.properties.required === false ? "5 4" : undefined,
            },
            labelStyle: {
              fill: "#9ca5b1",
              fontSize: 11,
              fontFamily: "monospace",
            },
            labelBgStyle: { fill: "#14171b", fillOpacity: 1 },
            markerEnd: {
              type: MarkerType.ArrowClosed,
              width: 16,
              height: 16,
              color: high ? "#d7b575" : "#58616b",
            },
          };
        }),
    };
  }, [
    graph,
    expanded,
    selected,
    contextFocus,
    run?.fault,
    run?.status,
    run?.experiments,
    latest?.checkout.ok,
    branch,
  ]);
  const status = running
    ? "Investigating"
    : ready
      ? "Repair verified"
      : recovered
        ? "Recovered"
        : run?.status === "stale"
          ? "Context changed"
          : run?.status === "unresolved"
            ? "No safe repair"
            : run?.fault
              ? "Incident active"
              : run
                ? "Systems healthy"
                : "Awaiting initialization";
  return (
    <div className="app-shell" data-theme="aftershock">
      <aside className="rail">
        <button
          className="brand"
          onClick={() => setTab("command")}
          aria-label="Aftershock home"
        >
          <span className="brand-symbol">
            <Activity size={21} strokeWidth={2.5} />
          </span>
          <span>
            aftershock<span className="brand-period">/</span>
          </span>
        </button>
        <div className="workspace-label">
          <span className="company-avatar">
            {config?.workspace_name?.[0] || "N"}
          </span>
          <div>
            <select
              className="select select-ghost select-xs workspace-select"
              aria-label="Select company workspace"
              value={config?.tenant_id || "northstar"}
              disabled={!!busy || running || config?.pool_busy}
              onChange={(event) => switchWorkspace(event.target.value)}
            >
              {(
                config?.workspaces || [
                  { id: "northstar", name: "Northstar Commerce" },
                ]
              ).map((workspace: any) => (
                <option key={workspace.id} value={workspace.id}>
                  {workspace.name}
                </option>
              ))}
            </select>
            <span>Isolated memory workspace</span>
          </div>
        </div>
        <div className="nav-label">Workspace</div>
        <div className="rail-nav menu">
          <button
            aria-label="Incident command"
            title="Incident command"
            className={tab === "command" ? "active" : ""}
            onClick={() => setTab("command")}
          >
            <Command size={16} />
            <span>Incident command</span>
            {run?.fault && !recovered && <span className="nav-count">1</span>}
          </button>
          <button
            aria-label="Persistent memory"
            title="Persistent memory"
            className={tab === "memory" ? "active" : ""}
            onClick={() => setTab("memory")}
          >
            <Clock3 size={16} />
            <span>Incident memory</span>
          </button>
          <button
            aria-label="Repair experiments"
            onClick={() => {
              setTab("command");
              requestAnimationFrame(() =>
                document
                  .getElementById("repair-experiments")
                  ?.scrollIntoView({ behavior: "smooth", block: "start" }),
              );
            }}
          >
            <GitBranch size={16} />
            <span>Repair experiments</span>
          </button>
          <button
            aria-label="Graph evidence"
            title="Graph evidence"
            onClick={() => {
              setTab("command");
              setExpanded(true);
              setContextFocus(null);
              requestAnimationFrame(() =>
                document
                  .getElementById("dependency-graph")
                  ?.scrollIntoView({ behavior: "smooth", block: "center" }),
              );
            }}
          >
            <Network size={16} />
            <span>Dependency graph</span>
          </button>
          <button
            aria-label="Company context"
            title="Sources and decisions"
            onClick={() => {
              setTab("command");
              requestAnimationFrame(() =>
                document
                  .getElementById("company-context")
                  ?.scrollIntoView({ behavior: "smooth", block: "start" }),
              );
            }}
          >
            <Users size={16} />
            <span>Company context</span>
          </button>
        </div>
        <div className="sidebar-context">
          <div className="nav-label">Environment</div>
          <span>
            <span className={`status-dot ${connected ? "green" : "gray"}`} />
            {connected ? "FalkorDB connected" : "Connecting graph"}
          </span>
          <span>
            <GitBranch size={13} />4 isolated sandboxes
          </span>
          <span>
            <ShieldCheck size={13} />
            Evidence required to act
          </span>
        </div>
        <div className="rail-bottom">
          <button
            aria-label="Help"
            className="sidebar-help"
            onClick={() => setHelp(true)}
          >
            <BookOpen size={16} />
            <span>Workspace guide</span>
            <ArrowUpRight size={13} />
          </button>
          <div className="sidebar-profile">
            <span className="avatar">NC</span>
            <div>
              <strong>{config?.workspace_name || "Northstar sandbox"}</strong>
              <span>Synthetic company</span>
            </div>
            <span className="status-dot green" />
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="top-location">
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>
              {tab === "memory" ? "Incident memory" : "Incident command"}
            </strong>
          </div>
          <div className="top-right">
            <select
              className="select select-sm mobile-workspace-select"
              aria-label="Switch company workspace"
              value={config?.tenant_id || "northstar"}
              disabled={!!busy || config?.pool_busy}
              onChange={(event) => switchWorkspace(event.target.value)}
            >
              {(
                config?.workspaces || [
                  { id: "northstar", name: "Northstar Commerce" },
                ]
              ).map((workspace: any) => (
                <option key={workspace.id} value={workspace.id}>
                  {workspace.name}
                </option>
              ))}
            </select>
            <span className="connection">
              <span className={`status-dot ${connected ? "green" : "gray"}`} />
              {connected ? "Graph connected" : "Local environment"}
            </span>
            <span className="badge badge-outline env-badge">Local sandbox</span>
            <button
              className="btn btn-ghost btn-sm btn-square icon-button"
              onClick={() => setHelp(true)}
              aria-label="Open guide"
            >
              <BookOpen size={17} />
            </button>
          </div>
        </header>
        <main>
          <section className="page-heading">
            <div>
              <h1>
                {tab === "memory" ? "Incident memory" : "Incident workspace"}
              </h1>
              <p>
                {tab === "memory"
                  ? "Verified outcomes, reusable procedures, and agent handoffs."
                  : "Follow the dependencies. Compare repairs. Verify the outcome."}
              </p>
            </div>
            <button
              className="btn btn-sm btn-ghost guide-button"
              onClick={() => setHelp(true)}
            >
              <BookOpen size={14} />
              Quick guide
              <ArrowUpRight size={13} />
            </button>
          </section>
          {config?.mode === "rehearsal" && (
            <div className="mode-notice">
              <Terminal size={15} />
              <strong>Rehearsal mode</strong>
              <span>
                Real services, graph queries and repair experiments.
                Deterministic agent adapter; no LLM calls.
              </span>
            </div>
          )}
          {config?.mode === "live" && config?.key_configured && (
            <div className="mode-notice live-mode">
              <Radio size={14} />
              <strong>Live agents</strong>
              <span>
                Graph context via MCP <span className="mode-separator">/</span>{" "}
                {config.model}
              </span>
            </div>
          )}
          {config?.mode === "live" && !config?.key_configured && (
            <div className="mode-notice">
              <Sparkles size={15} />
              <strong>Model key needed</strong>
              <span>
                Add GEMINI_API_KEY to .env and restart the API for live agents.
                Services and probes work independently.
              </span>
            </div>
          )}
          {error && (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <button onClick={() => setError("")} aria-label="Dismiss error">
                <X size={16} />
              </button>
            </div>
          )}
          {config?.can_control === false && (
            <div className="workspace-ownership mode-notice">
              <Database size={15} />
              <div>
                <strong>
                  Company memory is available. The sandbox is assigned to{" "}
                  {config.sandbox_owner || "a recovery operation"}.
                </strong>
                <p>
                  Activate this workspace to restore its saved services and
                  database.
                </p>
              </div>
              <button
                className="btn btn-outline btn-sm"
                disabled={!!busy || config.pool_busy}
                onClick={() =>
                  command("workspace", async () => {
                    await api(`/workspaces/${config.tenant_id}/activate`, {});
                    window.location.reload();
                  })
                }
              >
                Activate workspace
              </button>
            </div>
          )}
          {tab === "memory" ? (
            <section className="memory-section">
              <CoordinationProof
                report={coordination}
                workspace={config?.workspace_name || "Current workspace"}
              />
              <ProcedureMemory procedures={company?.procedures || []} />
              <div className="section-heading">
                <h2>
                  <Network size={17} /> Incident memory
                </h2>
                <span className="mono">PERSISTED IN FALKORDB</span>
              </div>
              {memory.filter((m) => m.outcome).length === 0 ? (
                <div className="empty-state">
                  <Network size={34} />
                  <h3>No outcomes recorded yet</h3>
                  <p>
                    Resolve an incident to give the next investigator a verified
                    experience to retrieve.
                  </p>
                </div>
              ) : (
                memory
                  .filter((m) => m.outcome)
                  .map((m) => (
                    <article className="memory-card" key={m.incident}>
                      <span className="badge neutral">{m.outcome.status}</span>
                      <h3>
                        {actions.find((a) => a.id === m.action)?.name ||
                          "No eligible repair"}
                      </h3>
                      <p>
                        Incident {m.incident} · Recommendations{" "}
                        {m.outcome.required ? "mandatory" : "optional"}
                      </p>
                      <div className="evidence-tags">
                        {m.outcome.evidence_ids?.map((id: string) => (
                          <code key={id}>{id}</code>
                        ))}
                      </div>
                    </article>
                  ))
              )}
              <ConversationMemory messages={conversation} />
            </section>
          ) : (
            <>
              <section className="incident-strip">
                <div className="incident-id">
                  <span
                    className={`incident-icon ${run?.fault && !recovered ? "incident-red" : ""}`}
                  >
                    <Activity size={20} />
                  </span>
                  <div>
                    <span className="mono">
                      {run
                        ? `INC-${run.id.slice(0, 4).toUpperCase()} / ${String(run.incident).padStart(2, "0")}`
                        : "Getting started"}
                    </span>
                    <h2>
                      {run?.fault
                        ? "Checkout dependency timeout"
                        : run
                          ? "All systems operational"
                          : "Set up your company"}
                    </h2>
                  </div>
                </div>
                <span
                  className={`badge ${recovered || (run && !run.fault) ? "success" : ready ? "warm" : run?.fault ? "danger" : "neutral"}`}
                >
                  <span className="status-dot" />
                  {status}
                </span>
                <div className="incident-meta">
                  <span>Company version</span>
                  <strong>{run ? `v${run.version}` : "—"}</strong>
                </div>
                <div className="incident-meta">
                  <span>Agent calls</span>
                  <strong>{run ? `${run.model_calls} / 12` : "—"}</strong>
                </div>
                <div className="incident-actions">
                  {!run ? (
                    <button
                      className="btn btn-primary btn-sm"
                      disabled={!!busy || config?.can_control === false}
                      onClick={() => command("initialize", initialize)}
                    >
                      {busy ? (
                        <Loader2 className="spin" size={16} />
                      ) : (
                        <Play size={15} />
                      )}{" "}
                      Initialize company
                    </button>
                  ) : (
                    <>
                      <button
                        className="btn btn-outline btn-sm"
                        disabled={
                          !!busy || running || config?.can_control === false
                        }
                        onClick={() => command("fault", () => act("fault"))}
                      >
                        <Zap size={14} />
                        {run.incident > 0 ? "Inject again" : "Inject fault"}
                      </button>
                      <button
                        className="btn btn-primary btn-sm"
                        disabled={
                          !!busy ||
                          config?.can_control === false ||
                          running ||
                          !run.fault ||
                          ready ||
                          recovered ||
                          run.status === "stale" ||
                          run.status === "unresolved"
                        }
                        onClick={() =>
                          command("investigate", () => act("investigate"))
                        }
                      >
                        {running ? (
                          <Loader2 className="spin" size={15} />
                        ) : (
                          <GitBranch size={15} />
                        )}{" "}
                        {running
                          ? "Investigating"
                          : run.status === "waiting" || run.status === "error"
                            ? "Resume investigation"
                            : "Investigate"}
                      </button>
                    </>
                  )}
                </div>
              </section>
              <div className="overview-metrics">
                {(["checkout", "billing"] as const).map((service) => (
                  <div key={service} className="overview-metric">
                    <span>
                      {service === "checkout" ? "Checkout" : "Billing"}
                      <span
                        className={`status-dot ${latest ? (latest[service].ok ? "green" : "red") : "gray"}`}
                      />
                    </span>
                    <strong>
                      {latest
                        ? latest[service].ok
                          ? "Healthy"
                          : "Failing"
                        : "Awaiting probes"}
                    </strong>
                    <small>
                      {latest
                        ? `HTTP ${latest[service].status} · ${Math.round(latest[service].duration_ms)} ms`
                        : "No requests observed yet"}
                    </small>
                  </div>
                ))}
                <div className="overview-metric">
                  <span>
                    Experiment branches
                    <GitBranch size={13} />
                  </span>
                  <strong>
                    {run?.experiments.filter((e) => e.status === "complete")
                      .length || 0}
                    <em> / {displayedActions.length}</em>
                  </strong>
                  <small>
                    {running
                      ? "Comparing isolated repairs"
                      : ready
                        ? "Ready for review"
                        : "Independent graph + service snapshots"}
                  </small>
                </div>
                <div className="overview-metric">
                  <span>
                    Company requirements
                    <ShieldCheck size={13} />
                  </span>
                  <strong>{run?.required ? "Strict" : "Standard"}</strong>
                  <small>
                    Recommendations {run?.required ? "required" : "optional"}
                  </small>
                </div>
              </div>
              <div className={`command-grid ${graphWide ? "graph-wide" : ""}`}>
                <section className="graph-panel panel" id="dependency-graph">
                  <div className="panel-heading">
                    <h2>
                      <Network size={16} /> Dependency graph{" "}
                      <span className="count">
                        {flow.nodes.length}
                        {graph && flow.nodes.length !== graph.nodes.length
                          ? ` of ${graph.nodes.length}`
                          : ""}{" "}
                        nodes
                      </span>
                    </h2>
                    <div className="graph-tools">
                      <button
                        className={`btn btn-ghost btn-xs ${expanded ? "selected" : ""}`}
                        onClick={() => {
                          if (contextFocus) {
                            setContextFocus(null);
                            setExpanded(true);
                          } else setExpanded(!expanded);
                        }}
                      >
                        <Layers3 size={13} />
                        {contextFocus
                          ? "Evidence path"
                          : expanded
                            ? "All context"
                            : "Services"}
                      </button>
                      <select
                        className="select select-sm"
                        aria-label="Select graph branch"
                        value={branch}
                        onChange={(e) => {
                          setBranch(e.target.value);
                          setGraphLoading(true);
                          setContextFocus(null);
                          setSelected([]);
                          setExpanded(false);
                        }}
                      >
                        <option value="company">Main company</option>
                        {run?.experiments.map((e) => (
                          <option value={e.action} key={e.action}>
                            {e.title}
                          </option>
                        ))}
                      </select>
                      <button
                        className="btn btn-ghost btn-xs btn-square"
                        aria-label={
                          graphWide ? "Collapse graph" : "Expand graph"
                        }
                        onClick={() => setGraphWide(!graphWide)}
                      >
                        <Maximize2 size={14} />
                      </button>
                    </div>
                  </div>
                  <div className="graph-canvas">
                    {graphLoading ? (
                      <div className="empty-state graph-empty" role="status">
                        <span className="loading loading-spinner loading-sm" />
                        <p>Loading graph context…</p>
                      </div>
                    ) : graph ? (
                      <ReactFlow
                        key={`${expanded ? "expanded" : "services"}-${compact ? "compact" : "wide"}-${graphWide}-${contextFocus?.join(":") || "all"}`}
                        nodes={flow.nodes}
                        edges={flow.edges}
                        nodeTypes={nodeTypes}
                        fitView
                        fitViewOptions={{ padding: compact ? 0.1 : 0.12 }}
                        minZoom={0.15}
                        maxZoom={1.6}
                        nodesDraggable={false}
                        nodesConnectable={false}
                        onNodeClick={(_, node) => setSelected([node.id])}
                        proOptions={{ hideAttribution: true }}
                      >
                        <Background color="#343a42" gap={24} size={1} />
                        <Controls showInteractive={false} />
                      </ReactFlow>
                    ) : (
                      <div className="empty-state graph-empty">
                        <div className="empty-orbit">
                          <Network size={30} />
                        </div>
                        <h3>No company graph yet</h3>
                        <p>
                          Initialize the environment to load its operational
                          graph
                          <br />
                          and start five working HTTP services.
                        </p>
                      </div>
                    )}
                    <div className="graph-key">
                      <span>
                        <i className="key-line" /> Required dependency
                      </span>
                      <span>
                        <i className="key-line dashed" /> Optional dependency
                      </span>
                    </div>
                  </div>
                  <div className="graph-footer">
                    <span>
                      <span
                        className={`status-dot ${connected ? "green" : "gray"}`}
                      />{" "}
                      {branch === "company"
                        ? "Main company"
                        : "Isolated graph copy"}
                    </span>
                    <span>
                      {selected.length ? (
                        <button
                          onClick={() => {
                            setSelected([]);
                            setContextFocus(null);
                          }}
                        >
                          Clear highlighted evidence <X size={12} />
                        </button>
                      ) : (
                        "Select a node to highlight its evidence"
                      )}{" "}
                      <GitBranch size={13} />
                    </span>
                  </div>
                </section>
                <section className="activity-panel panel">
                  <div className="panel-heading">
                    <h2>
                      <Radio size={16} /> Agent activity
                    </h2>
                    <span className="live-label">
                      <span
                        className={`status-dot ${running ? "orange" : "green"}`}
                      />
                      {running ? "Working" : "Live"}
                    </span>
                  </div>
                  <div className="agent-roles">
                    {["investigator", "coordinator", "verifier"].map(
                      (role, i) => (
                        <div
                          key={role}
                          className={
                            events.at(-1)?.role === role ? "current" : ""
                          }
                        >
                          <span>0{i + 1}</span>
                          <strong>
                            {role === "coordinator"
                              ? "Experimenter"
                              : role[0].toUpperCase() + role.slice(1)}
                          </strong>
                          <span
                            className={`status-dot ${events.some((e) => e.role === role) ? "green" : "gray"}`}
                          />
                        </div>
                      ),
                    )}
                  </div>
                  <div className="activity-feed">
                    {events.length === 0 ? (
                      <div className="feed-empty">
                        <Clock3 size={21} />
                        <p>Waiting for the first event.</p>
                        <span>Every handoff leaves an evidence trail.</span>
                      </div>
                    ) : (
                      events
                        .slice(-30)
                        .reverse()
                        .map((e) => (
                          <button
                            className="event-item"
                            key={e.sequence}
                            onClick={() => {
                              setSelected(e.evidence_ids || []);
                              setContextFocus(null);
                            }}
                          >
                            <span
                              className={`event-marker ${e.role === "verifier" ? "verifier" : ""}`}
                            >
                              {e.role === "verifier" ? (
                                <ShieldCheck size={13} />
                              ) : e.role === "investigator" ? (
                                <Network size={13} />
                              ) : (
                                <GitBranch size={13} />
                              )}
                            </span>
                            <div>
                              <div className="event-label">
                                <strong>{e.title}</strong>
                                <time>{time(e.at)}</time>
                              </div>
                              <p>{e.detail}</p>
                              <span className="event-role">
                                {e.role.toUpperCase()}
                                {e.evidence_ids?.length
                                  ? ` · ${e.evidence_ids.length} evidence links`
                                  : ""}
                              </span>
                            </div>
                          </button>
                        ))
                    )}
                  </div>
                  <div className="activity-footer">
                    <Database size={12} /> Persisted handoffs · resumable event
                    stream
                  </div>
                </section>
              </div>
              <section className="futures-section" id="repair-experiments">
                <div className="section-heading">
                  <div>
                    <h2>
                      <GitBranch size={18} /> Repair experiments{" "}
                      <span className="count">{displayedActions.length}</span>
                    </h2>
                    <p>
                      One snapshot. Isolated environments. Actual HTTP evidence.
                    </p>
                  </div>
                  <span className="mono">
                    <span className="status-dot orange" />{" "}
                    {run?.experiments.filter((e) => e.status === "complete")
                      .length || 0}{" "}
                    / {displayedActions.length} complete
                  </span>
                </div>
                <DecisionChange
                  data={decisionDiff}
                  onSelect={(ids) => {
                    setSelected(ids);
                    setContextFocus(ids);
                    setExpanded(true);
                    document
                      .getElementById("dependency-graph")
                      ?.scrollIntoView({ behavior: "smooth", block: "center" });
                  }}
                />
                <div
                  className="experiment-grid"
                  data-count={displayedActions.length}
                >
                  {displayedActions.map((action, index) => {
                    const e = run?.experiments.find(
                      (e) => e.action === action.id,
                    );
                    const passed = e?.verdict?.passed;
                    const candidate = company?.candidates.find(
                      (c) => c.action === action.id,
                    );
                    const Icon = action.icon;
                    return (
                      <article
                        className={`experiment-card ${e?.verdict ? (passed ? "passed" : "rejected") : ""} ${e?.status === "running" ? "executing" : ""}`}
                        key={action.id}
                      >
                        <div className="experiment-top">
                          <span className="universe-label">
                            BRANCH / 0{index + 1}
                          </span>
                          <span
                            className={`badge ${e?.verdict ? (passed ? "success" : "danger") : "neutral"}`}
                          >
                            {e?.verdict ? (
                              passed ? (
                                <>
                                  <Check size={12} />
                                  Verified
                                </>
                              ) : (
                                <>
                                  <X size={12} />
                                  Rejected
                                </>
                              )
                            ) : e?.status === "running" ? (
                              <>
                                <Loader2 className="spin" size={12} />
                                Running
                              </>
                            ) : (
                              "Pending"
                            )}
                          </span>
                        </div>
                        <div className="experiment-title">
                          <span className="action-icon">
                            <Icon size={19} />
                          </span>
                          <h3>{action.name}</h3>
                        </div>
                        <p className="action-description">
                          {action.description}
                        </p>
                        <div className="prediction">
                          <span>Predicted impact</span>
                          <p>
                            {e?.prediction.reason ||
                              candidate?.prediction.reason ||
                              "Initialize the company to retrieve graph requirements."}
                          </p>
                        </div>
                        <div className="experiment-observations">
                          <span>Observed impact</span>
                          {e?.verdict ? (
                            <div className="observed-grid">
                              <div>
                                <span
                                  className={`probe-status ${e.observations.slice(-3).every((p) => p.checkout.ok) ? "ok" : "bad"}`}
                                />
                                <strong>Checkout</strong>
                                <span>
                                  {e.observations
                                    .slice(-3)
                                    .every((p) => p.checkout.ok)
                                    ? "Recovered"
                                    : "Failing"}
                                </span>
                              </div>
                              <div>
                                <span
                                  className={`probe-status ${e.verdict.billing_failures ? "bad" : "ok"}`}
                                />
                                <strong>Billing</strong>
                                <span>
                                  {e.verdict.billing_failures
                                    ? `${e.verdict.billing_failures} failed probes`
                                    : "Unaffected"}
                                </span>
                              </div>
                            </div>
                          ) : (
                            <p className="pending-observation">
                              {e?.status === "running"
                                ? "Running requests through the isolated company…"
                                : "Waiting for runtime verification"}
                            </p>
                          )}
                        </div>
                        <div className="experiment-bottom">
                          <span className="mono">
                            {e?.duration_ms
                              ? `${(e.duration_ms / 1000).toFixed(1)}s · ${e.observations.length} probes`
                              : "Isolated sandbox"}
                          </span>
                          <button
                            disabled={!e}
                            onClick={() => {
                              setDrawer(e || null);
                              setSelected(e?.prediction.evidence_ids || []);
                            }}
                          >
                            Inspect evidence <ArrowUpRight size={14} />
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              </section>
              {ready && (
                <section className="decision-banner">
                  <div className="decision-icon">
                    <ShieldCheck size={23} />
                  </div>
                  <div>
                    <span className="eyebrow">VERIFIED RECOMMENDATION</span>
                    <h3>Graceful fallback is ready to apply</h3>
                    <p>
                      Graceful fallback passed graph requirements and
                      independent runtime probes.
                    </p>
                  </div>
                  <button
                    className="btn btn-primary btn-sm"
                    disabled={!!busy || config?.can_control === false}
                    onClick={() =>
                      command("apply", () =>
                        act("apply", {
                          idempotency_key: `repair-${run!.id}-${run!.incident}`,
                        }),
                      )
                    }
                  >
                    {busy === "apply" ? (
                      <Loader2 className="spin" size={16} />
                    ) : (
                      <CheckCheck size={16} />
                    )}{" "}
                    Apply verified repair <ArrowRight size={15} />
                  </button>
                </section>
              )}
              {recovered && (
                <section className="decision-banner recovered">
                  <div className="decision-icon">
                    <CheckCheck size={24} />
                  </div>
                  <div>
                    <span className="eyebrow">RECOVERY VERIFIED</span>
                    <h3>Checkout recovered. Procedure saved.</h3>
                    <p>
                      Three successful checkout and billing probes. The next
                      investigator can retrieve this outcome.
                    </p>
                  </div>
                  <button
                    className="btn btn-outline btn-sm"
                    onClick={() => setTab("memory")}
                  >
                    View incident memory <ArrowUpRight size={14} />
                  </button>
                </section>
              )}
              {run?.status === "unresolved" && (
                <section className="decision-banner unresolved">
                  <div className="decision-icon">
                    <ShieldCheck size={24} />
                  </div>
                  <div>
                    <span className="eyebrow">NO ELIGIBLE REPAIR</span>
                    <h3>No repair satisfies the current requirements</h3>
                    <p>
                      Current graph requirements invalidate the bypass. All
                      available interventions were rejected.
                    </p>
                    {run.escalation && (
                      <p>
                        Internal escalation assigned to{" "}
                        {run.escalation.owner.name} ·{" "}
                        {run.escalation.owner.team}.
                      </p>
                    )}
                  </div>
                </section>
              )}
              <KnowledgePanel
                context={company}
                onSelect={(ids) => {
                  setSelected(ids);
                  setExpanded(true);
                  setContextFocus(ids);
                  document
                    .getElementById("dependency-graph")
                    ?.scrollIntoView({ behavior: "smooth", block: "center" });
                }}
              />
              <section className="bottom-grid">
                <div className="probe-panel panel">
                  <div className="panel-heading">
                    <h2>
                      <Activity size={16} /> Main environment probes
                    </h2>
                    <span className="live-label">
                      <span className="status-dot green" />
                      Live HTTP
                    </span>
                  </div>
                  <div className="probe-rows">
                    {(["checkout", "billing"] as const).map((role) => (
                      <div className="probe-row" key={role}>
                        <span
                          className={`status-dot ${latest ? (latest[role].ok ? "green" : "red") : "gray"}`}
                        />
                        <strong>
                          {role === "checkout" ? "Checkout" : "Billing"}
                        </strong>
                        <div className="probe-bars">
                          {samples.slice(-32).map((s, i) => (
                            <span
                              key={`${s.at}-${i}`}
                              className={s[role].ok ? "good" : "bad"}
                              title={`${time(s.at)} · HTTP ${s[role].status} · ${s[role].duration_ms}ms`}
                            />
                          ))}
                        </div>
                        <span className="mono">
                          {latest
                            ? `${latest[role].duration_ms.toFixed(0)} ms`
                            : "—"}
                        </span>
                        <span
                          className={`http-code ${latest && !latest[role].ok ? "bad" : ""}`}
                        >
                          {latest
                            ? `HTTP ${latest[role].status}`
                            : "NO SAMPLES"}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="probe-caption">
                    {samples.length
                      ? `${samples.length} recent observations · refreshed every 2 seconds`
                      : "Initialize the company to begin observing actual requests."}
                  </div>
                </div>
                <div className="scenario-panel panel">
                  <div className="panel-heading">
                    <h2>
                      <Workflow size={16} /> Policy controls
                    </h2>
                    <span className="count">Scenario 02</span>
                  </div>
                  <p>
                    Update the requirement, then investigate another incident.
                  </p>
                  <label
                    className={`policy-toggle ${run?.required ? "on" : ""}`}
                  >
                    <input
                      className="toggle toggle-sm toggle-primary"
                      type="checkbox"
                      aria-label="Mandatory recommendations"
                      checked={pendingPolicy ?? !!run?.required}
                      disabled={
                        !run ||
                        !!busy ||
                        running ||
                        config?.can_control === false
                      }
                      aria-busy={pendingPolicy !== null}
                      onChange={(event) => {
                        const required = event.currentTarget.checked;
                        setPendingPolicy(required);
                        command("policy", async () => {
                          try {
                            await act("policy", { required });
                          } finally {
                            setPendingPolicy(null);
                          }
                        });
                      }}
                    />
                    <span>
                      <strong>Mandatory recommendations</strong>
                      <small>
                        {pendingPolicy !== null
                          ? "Updating company requirement…"
                          : run?.required
                            ? "Required by current company policy"
                            : "Currently optional · fallback permitted"}
                      </small>
                    </span>
                  </label>
                  <div className="scenario-hint">
                    <ArrowDownLeft size={14} /> Change the policy, then inject
                    the incident again.
                  </div>
                </div>
              </section>
              <div className="workspace-footer">
                <span>
                  <Database size={12} /> Context and memory in FalkorDB
                </span>
                <div>
                  <span>
                    {lastUpdate
                      ? `Last graph event ${new Date(lastUpdate).toLocaleTimeString()}`
                      : "Ready when you are"}
                  </span>
                  {run && (
                    <button
                      disabled={
                        !!busy || running || config?.can_control === false
                      }
                      onClick={() =>
                        command("reset", async () => {
                          await act("reset");
                          setRun(null);
                          setGraph(null);
                          setEvents([]);
                          setSamples([]);
                          setContextFocus(null);
                          setSelected([]);
                          setExpanded(false);
                        })
                      }
                    >
                      <RotateCcw size={12} />
                      Reset workspace
                    </button>
                  )}
                </div>
              </div>
            </>
          )}
        </main>
      </div>
      {drawer && (
        <div className="drawer-backdrop" onClick={() => setDrawer(null)}>
          <aside
            className="evidence-drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="evidence-heading"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="drawer-heading">
              <div>
                <span className="eyebrow">EXPERIMENT EVIDENCE</span>
                <h2 id="evidence-heading">{drawer.title}</h2>
              </div>
              <button
                onClick={() => setDrawer(null)}
                aria-label="Close evidence"
              >
                <X size={20} />
              </button>
            </div>
            <span
              className={`badge ${drawer.verdict?.passed ? "success" : "danger"}`}
            >
              {drawer.verdict?.passed ? "Verified" : "Rejected"}
            </span>
            <h3>Why this decision?</h3>
            {drawer.verdict?.reasons.map((reason) => (
              <p key={reason}>{reason}</p>
            ))}
            <h3>Snapshot provenance</h3>
            <dl>
              <dt>Company version</dt>
              <dd>v{drawer.version}</dd>
              <dt>Snapshot SHA-256</dt>
              <dd className="mono wrap">{drawer.checksum}</dd>
              <dt>Graph branch</dt>
              <dd className="mono wrap">{drawer.graph}</dd>
            </dl>
            <h3>Supporting graph facts</h3>
            <div className="evidence-tags">
              {drawer.prediction.evidence_ids.map((id) => (
                <button
                  key={id}
                  onClick={() => {
                    setSelected([id]);
                    setExpanded(true);
                    setContextFocus([id]);
                  }}
                >
                  {id}
                  <ArrowUpRight size={11} />
                </button>
              ))}
            </div>
            <h3>Cypher · predicted impact</h3>
            <pre>{drawer.prediction.query}</pre>
            <h3>Observed impact · HTTP probes</h3>
            <table className="table table-sm">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Checkout</th>
                  <th>Billing</th>
                </tr>
              </thead>
              <tbody>
                {drawer.observations.map((sample, i) => (
                  <tr key={i}>
                    <td>{time(sample.at)}</td>
                    <td
                      className={sample.checkout.ok ? "text-green" : "text-red"}
                    >
                      {sample.checkout.status}
                    </td>
                    <td
                      className={sample.billing.ok ? "text-green" : "text-red"}
                    >
                      {sample.billing.status}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {drawer.processes_before && (
              <>
                <h3>Actual process changes</h3>
                <pre>
                  {Object.keys(drawer.processes_before)
                    .map(
                      (role) =>
                        `${role}: ${drawer.processes_before![role].pid} → ${drawer.processes_after?.[role]?.pid}`,
                    )
                    .join("\n")}
                </pre>
              </>
            )}
          </aside>
        </div>
      )}
      {help && (
        <div className="modal-backdrop" onClick={() => setHelp(false)}>
          <section
            className="help-modal modal-box"
            role="dialog"
            aria-modal="true"
            aria-labelledby="guide-heading"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close"
              onClick={() => setHelp(false)}
              aria-label="Close guide"
            >
              <X size={20} />
            </button>
            <div className="eyebrow">Workspace guide</div>
            <h2 id="guide-heading">From incident to verified repair</h2>
            <p>
              One working company. Three isolated futures. FalkorDB connects
              operational facts, agent handoffs and verified experience.
            </p>
            <ol>
              <li>
                <strong>Initialize the company</strong>
                <span>
                  Five real HTTP processes and an independent SQLite database in
                  each environment.
                </span>
              </li>
              <li>
                <strong>Inject a failure, then investigate</strong>
                <span>
                  Agents read evidence and coordinate three experiments through
                  persistent graph state.
                </span>
              </li>
              <li>
                <strong>Inspect and apply the verified repair</strong>
                <span>
                  Actual runtime probes decide whether a repair passes.
                </span>
              </li>
              <li>
                <strong>Change the policy and try again</strong>
                <span>
                  Watch current requirements invalidate a remembered repair.
                </span>
              </li>
            </ol>
            <div className="help-note">
              <Terminal size={16} />
              <span>
                Restart the controller with{" "}
                <code>docker compose restart api</code>. Agent tasks, events,
                experiment results and incident memory persist in FalkorDB.
              </span>
            </div>
            <a href="/docs" target="_blank" rel="noreferrer">
              Open API documentation <ExternalLink size={14} />
            </a>
          </section>
        </div>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
