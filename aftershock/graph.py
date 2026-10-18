"""All operational decisions and durable coordination depend on FalkorDB."""

import json
import os
import time
import uuid
import re
from pathlib import Path
from falkordb import FalkorDB
from aftershock.domain import Action
from aftershock.knowledge import Knowledge, BFS_QUERY
from aftershock.embeddings import Embeddings
from aftershock.provenance import Provenance

FIXTURE = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "northstar.json").read_text()
)
SEED_NODES = [
    (item["label"], id_, {k: v for k, v in item.items() if k != "label"})
    for id_, item in FIXTURE.items()
    if "label" in item
]
SEED_EDGES = [
    (
        item["from"],
        item["to"],
        item["type"],
        {k: v for k, v in item.items() if k not in ("from", "to", "type")},
    )
    for item in FIXTURE.values()
    if "type" in item
]

DEPENDENCY_QUERY = """MATCH p=(s:Service {id:$service})-[:DEPENDS_ON*1..4]->(d:Service)
RETURN [n IN nodes(p) | n.id] AS nodes, [r IN relationships(p) | r.id] AS edges"""
IMPACT_QUERY = """MATCH p=(s:Service)-[:DEPENDS_ON*0..4]->(target:Service {id:$target}),
(s)-[:SUPPORTS]->(w:Workflow)-[:USED_BY]->(c:CustomerGroup)
RETURN DISTINCT s.id, w.id, c.id, [r IN relationships(p) | r.id]"""


class GraphStore(Knowledge, Provenance):
    def __init__(self, prefix=None, tenant=None):
        self.base_prefix = prefix or os.environ.get("GRAPH_PREFIX", "aftershock")
        self.tenant = tenant or os.environ.get("AFTERSHOCK_TENANT", "northstar")
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", self.tenant):
            raise ValueError("Invalid tenant scope")
        self.prefix = (
            self.base_prefix
            if self.tenant == "northstar"
            else f"{self.base_prefix}__tenant_{self.tenant}"
        )
        self.db = FalkorDB(
            host=os.environ.get("FALKOR_HOST", "127.0.0.1"),
            port=int(os.environ.get("FALKOR_PORT", "6379")),
            password=os.environ.get("FALKOR_PASSWORD") or None,
            socket_timeout=5,
            socket_connect_timeout=3,
        )
        self.memory_name = f"{self.prefix}_memory"
        self.memory = self.db.select_graph(self.memory_name)
        self.embeddings = Embeddings(self)

    def q(self, query, params=None, graph=None):
        self.require_graph(graph or self.memory_name)
        return (
            (self.db.select_graph(graph) if graph else self.memory)
            .query(query, params or {})
            .result_set
        )

    def require_graph(self, name):
        if name != self.memory_name and not name.startswith(f"{self.prefix}_company_"):
            raise ValueError("Graph is outside the bound tenant scope")

    def initialize(self):
        self.q(
            "MERGE (c:Control {id:'singleton'}) ON CREATE SET c.active_run='', c.sequence=0"
        )
        try:
            self.q("CALL db.idx.fulltext.createNodeIndex('Incident', 'search_text')")
        except Exception as error:
            if "already" not in str(error).lower():
                raise
        self.initialize_knowledge()

    def active(self):
        rows = self.q("MATCH (c:Control {id:'singleton'}) RETURN c.active_run")
        return rows[0][0] if rows and rows[0][0] else None

    def create_run(self, name):
        run_id = uuid.uuid4().hex[:12]
        claimed = self.q(
            "MATCH (c:Control {id:'singleton'}) WHERE c.active_run='' SET c.active_run=$id RETURN c.active_run",
            {"id": run_id},
        )
        if not claimed:
            raise ValueError("Reset the active run before creating another company.")
        record = {
            "id": run_id,
            "tenant_id": self.tenant,
            "name": name,
            "company_graph": f"{self.prefix}_company_{run_id}",
            "version": 1,
            "status": "healthy",
            "fault": False,
            "required": False,
            "incident": 0,
            "experiments": [],
            "recommendation": None,
            "created_at": time.time(),
            "error": None,
            "model_calls": 0,
            "knowledge_version": 3,
        }
        self.q(
            "CREATE (r:Run {id:$id,payload:$payload})",
            {"id": run_id, "payload": json.dumps(record)},
        )
        self.seed(record["company_graph"])
        self.event(
            run_id,
            "system",
            "Company initialized",
            "Five working services are ready. All state is persisted in FalkorDB.",
        )
        return record

    def seed(self, graph):
        for label, id_, attrs in SEED_NODES:
            props = {"id": id_, "source": f"fixtures/northstar.json#{id_}", **attrs}
            self.q(
                f"MERGE (n:{label} {{id:$id}}) ON CREATE SET n=$props",
                {"id": id_, "props": props},
                graph,
            )
        for a, b, kind, attrs in SEED_EDGES:
            props = {
                "id": f"{a}:{kind}:{b}",
                "source": f"fixtures/northstar.json#{a}-{b}",
                **attrs,
            }
            self.q(
                f"MATCH (a {{id:$a}}),(b {{id:$b}}) MERGE (a)-[r:{kind} {{id:$id}}]->(b) ON CREATE SET r=$props",
                {"a": a, "b": b, "id": props["id"], "props": props},
                graph,
            )
        self.create_index(
            "CALL db.idx.fulltext.createNodeIndex('Document','text','name')",
            graph=graph,
        )
        for label in [
            "Service",
            "Person",
            "Policy",
            "Document",
            "Repair",
            "Decision",
            "Project",
            "Deployment",
            "Migration",
        ]:
            self.create_index(f"CREATE INDEX FOR (n:{label}) ON (n.id)", graph)
        self.create_index(
            "CREATE VECTOR INDEX FOR (n:Document) ON (n.embedding) OPTIONS {dimension:768,similarityFunction:'cosine'}",
            graph,
        )

    def upgrade_context(self, run):
        previous = run.get("knowledge_version", 1)
        if previous < 3:
            self.seed(run["company_graph"])
            # Preserve an already changed policy when adding the new provenance model.
            if previous < 2 and run.get("required"):
                self.record_policy_decision(run["company_graph"], True)
            run["knowledge_version"] = 3
            run["tenant_id"] = self.tenant
            self.save(run)

    def get(self, run_id):
        rows = self.q("MATCH (r:Run {id:$id}) RETURN r.payload", {"id": run_id})
        if not rows:
            raise KeyError(run_id)
        return json.loads(rows[0][0])

    def save(self, run):
        self.q(
            "MATCH (r:Run {id:$id}) SET r.payload=$payload",
            {"id": run["id"], "payload": json.dumps(run)},
        )

    def event(self, run_id, role, title, detail, **data):
        event_id = uuid.uuid4().hex
        body = {
            "role": role,
            "title": title,
            "detail": detail,
            "at": time.time(),
            **data,
        }
        self.q(
            """MATCH (c:Control {id:'singleton'}),(r:Run {id:$run})
SET c.sequence=c.sequence+1 CREATE (r)-[:HAS_EVENT]->(e:Event {id:$id,sequence:c.sequence,payload:$payload})""",
            {"run": run_id, "id": event_id, "payload": json.dumps(body)},
        )

    def events(self, run_id, after=0):
        rows = self.q(
            "MATCH (:Run {id:$run})-[:HAS_EVENT]->(e:Event) WHERE e.sequence>$after RETURN e.sequence,e.payload ORDER BY e.sequence",
            {"run": run_id, "after": after},
        )
        return [{"sequence": seq, **json.loads(payload)} for seq, payload in rows]

    def incident(self, run):
        id_ = f"{run['id']}_{run['incident']}"
        self.q(
            "MATCH (r:Run {id:$run}) CREATE (i:Incident {id:$id,run_id:$run,search_text:$text,version:$version}) CREATE (r)-[:HAS_INCIDENT]->(i)",
            {
                "id": id_,
                "run": run["id"],
                "version": run["version"],
                "text": "checkout recommendations timeout incident "
                + ("mandatory policy" if run["required"] else "optional fallback"),
            },
        )
        return id_

    def remember(self, run, outcome):
        id_ = f"{run['id']}_{run['incident']}"
        self.q(
            "MATCH (i:Incident {id:$id}) SET i.outcome=$outcome,i.action=$action,i.recorded_at=$at",
            {
                "id": id_,
                "outcome": json.dumps(outcome),
                "action": outcome.get("action", "none"),
                "at": time.time(),
            },
        )
        self.q(
            "MATCH (i:Incident {id:$id}) MERGE (o:Outcome {id:$id}) SET o.payload=$payload,o.status=$status MERGE (i)-[:RESULTED_IN]->(o)",
            {"id": id_, "payload": json.dumps(outcome), "status": outcome["status"]},
        )
        self.memory_entry(
            id_,
            "episodic",
            f"Checkout recommendations timeout. Action {outcome.get('action')}; result {outcome['status']}; recommendations required={run['required']}.",
            id_,
        )
        self.learn_procedure(run, outcome)

    def search_memory(self):
        rows = self.q(
            "CALL db.idx.fulltext.queryNodes('Incident','checkout recommendations') YIELD node RETURN node.id,node.action,node.outcome ORDER BY node.recorded_at DESC LIMIT 5"
        )
        return [
            {
                "incident": id_,
                "action": action,
                "outcome": json.loads(outcome) if outcome else None,
            }
            for id_, action, outcome in rows
        ]

    def dependencies(self, graph):
        rows = self.q(DEPENDENCY_QUERY, {"service": "checkout"}, graph)
        bfs = self.q(BFS_QUERY, {"service": "checkout"}, graph)
        return {
            "paths": [{"nodes": nodes, "edges": edges} for nodes, edges in rows],
            "query": DEPENDENCY_QUERY,
            "algorithm": {
                "name": "algo.bfs",
                "reachable_nodes": bfs[0][0] if bfs else [],
                "edges": bfs[0][1] if bfs else [],
                "query": BFS_QUERY,
            },
        }

    def evidence(self, graph):
        rows = self.q(
            "CALL db.idx.fulltext.queryNodes('Document','checkout timeout') YIELD node RETURN node.id,node.text,node.source",
            graph=graph,
        )
        return [
            {"id": id_, "text": text, "source": source} for id_, text, source in rows
        ]

    def predict(self, graph, action):
        target = "data" if action == Action.RESTART else "checkout"
        rows = self.q(IMPACT_QUERY, {"target": target}, graph)
        evidence = [edge for _, _, _, edges in rows for edge in edges]
        groups = sorted({group for _, _, group, _ in rows})
        eligible, reason = (
            True,
            "Dependency and policy checks passed. Runtime verification is still required.",
        )
        if action == Action.ROLLBACK:
            rows = self.q(
                "MATCH (:Service {id:'checkout'})-[r:REQUIRES_SCHEMA {checkout_version:1}]->(needed:Schema),(:Service {id:'data'})-[s:SUPPORTS]->(actual:Schema) RETURN needed.version,actual.version,r.id,s.id",
                graph=graph,
            )
            if not rows:
                raise ValueError("Missing schema evidence; rollback cannot be verified")
            required, actual, rid, sid = rows[0]
            evidence += [rid, sid]
            eligible = required == actual
            reason = f"Checkout v1 requires schema v{required}; shared data supports v{actual}."
            deployments = self.deployment_context(graph)
            if not deployments:
                eligible = False
                reason += " Current deployment and migration provenance is missing; rollback cannot be authorized."
            else:
                for deployment in deployments:
                    evidence += deployment["evidence_ids"]
                    reason += f" {deployment['name']} applied {deployment['migration']['name']}, approved by {deployment['owner']['name']}."
                    if (
                        not deployment["migration"]["backward_compatible"]
                        and required != actual
                    ):
                        eligible = False
                        reason += " Restarting checkout v1 does not reverse this incompatible migration."
        elif action == Action.FALLBACK:
            rows = self.q(
                "MATCH (:Service {id:'checkout'})-[d:DEPENDS_ON]->(:Service {id:'recommendations'}),(:Service {id:'checkout'})-[g:GOVERNED_BY]->(p:Policy) RETURN d.required,p.required,d.id,g.id,p.id",
                graph=graph,
            )
            if not rows:
                raise ValueError(
                    "Missing dependency or policy evidence; bypass cannot be verified"
                )
            required, policy, did, gid, pid = rows[0]
            evidence += [did, gid, pid]
            eligible = not required and not policy
            reason = (
                "Recommendations are mandatory; bypass would violate the current policy."
                if not eligible
                else "Recommendations are optional; graceful fallback is eligible for testing."
            )
            approvals = self.q(
                """MATCH (owner:Person)-[:OWNS]->(:Service {id:'checkout'}),
(owner)-[:APPROVED]->(d:Decision)-[:AFFECTS]->(project:Project)-[:INCLUDES]->(:Service {id:'checkout'}),
(d)-[:ESTABLISHES]->(:Policy {id:'policy-recommendations'}),(d)-[:CITES]->(source:Document)
WHERE d.current=true RETURN d.id,d.required,source.id,owner.id,project.id""",
                graph=graph,
            )
            if not approvals:
                eligible = False
                reason = "No current owner-approved project decision supports bypassing this dependency."
            else:
                evidence += [
                    item
                    for row in approvals
                    for item in (row[0], row[2], row[3], row[4])
                ]
                if any(row[1] for row in approvals):
                    eligible = False
                    reason = "The current owner-approved project decision requires recommendations; the remembered bypass is no longer permitted."
        elif action == Action.RESTART:
            reason = "Shared data supports checkout and billing. Restart may interrupt both workflows and does not address the recommendations fault."
        else:
            raise ValueError("Unknown action")
        return {
            "eligible": eligible,
            "reason": reason,
            "evidence_ids": sorted(set(evidence)),
            "affected_customer_groups": len(groups),
            "customer_groups": groups,
            "query": IMPACT_QUERY,
            "source_graph": graph,
        }

    def copy(self, src, dest):
        self.require_graph(src)
        self.require_graph(dest)
        self.db.select_graph(src).copy(dest)

    def mutate_branch(self, graph, action):
        if action == Action.ROLLBACK:
            self.q("MATCH (s:Service {id:'checkout'}) SET s.version=1", graph=graph)
        elif action == Action.FALLBACK:
            self.q("MATCH (s:Service {id:'checkout'}) SET s.fallback=true", graph=graph)
        else:
            self.q(
                "MATCH (s:Service {id:'data'}) SET s.intervention='restart'",
                graph=graph,
            )

    def policy(self, graph, required):
        self.q(
            "MATCH (checkout:Service {id:'checkout'})-[d:DEPENDS_ON]->(:Service {id:'recommendations'}),(p:Policy {id:'policy-recommendations'}) SET d.required=$required,p.required=$required,p.name=$name,checkout.fallback=false",
            {
                "required": required,
                "name": "Recommendations mandatory"
                if required
                else "Recommendations optional",
            },
            graph,
        )
        return self.record_policy_decision(graph, required)

    def projection(self, graph):
        nodes = self.q("MATCH (n) RETURN n.id,labels(n),properties(n)", graph=graph)
        edges = self.q(
            "MATCH (a)-[r]->(b) RETURN a.id,b.id,type(r),properties(r)", graph=graph
        )
        return {
            "name": graph,
            "nodes": [
                {
                    "id": id_,
                    "labels": labels,
                    "properties": {
                        k: v
                        for k, v in props.items()
                        if k
                        not in ("embedding", "embedding_model", "embedding_text_hash")
                    },
                }
                for id_, labels, props in nodes
            ],
            "edges": [
                {"source": a, "target": b, "type": kind, "properties": props}
                for a, b, kind, props in edges
            ],
        }

    def task(self, run, role):
        id_ = f"{run['id']}_{run['incident']}_{role}"
        self.q(
            "MERGE (t:Task {id:$id}) ON CREATE SET t.status='pending',t.lease=0,t.role=$role,t.run_id=$run",
            {"id": id_, "role": role, "run": run["id"]},
        )
        self.q(
            "MATCH (t:Task {id:$id}) MERGE (a:Agent {id:$role}) MERGE (a)-[:HANDLES]->(t)",
            {"id": id_, "role": role},
        )
        return id_

    def claim(self, id_, owner, lease=90):
        return bool(
            self.q(
                "MATCH (t:Task {id:$id}) WHERE t.status<>'done' AND (t.lease<$now OR t.owner=$owner) SET t.owner=$owner,t.lease=$until,t.status='running' RETURN t.id",
                {
                    "id": id_,
                    "owner": owner,
                    "now": time.time(),
                    "until": time.time() + lease,
                },
            )
        )

    def finish_task(self, id_, owner, payload):
        self.q(
            "MATCH (t:Task {id:$id}) WHERE t.owner=$owner SET t.status='done',t.lease=0,t.payload=$payload",
            {"id": id_, "owner": owner, "payload": json.dumps(payload)},
        )

    def task_result(self, id_):
        rows = self.q(
            "MATCH (t:Task {id:$id}) WHERE t.status='done' RETURN t.payload",
            {"id": id_},
        )
        return json.loads(rows[0][0]) if rows else None

    def release(self, id_, owner):
        self.q(
            "MATCH (t:Task {id:$id}) WHERE t.owner=$owner AND t.status='running' SET t.lease=0,t.status='pending'",
            {"id": id_, "owner": owner},
        )

    def save_experiment(self, run, experiment):
        id_ = f"{run['id']}_{run['incident']}_{experiment['action']}"
        self.q(
            """MATCH (i:Incident {id:$incident}) MERGE (e:Experiment {id:$id})
SET e.payload=$payload,e.run_id=$run,e.incident_number=$number,e.action=$action
MERGE (i)-[:HAS_EXPERIMENT]->(e)
MERGE (a:Action {id:$action}) MERGE (e)-[:TESTS]->(a)""",
            {
                "incident": f"{run['id']}_{run['incident']}",
                "id": id_,
                "payload": json.dumps(experiment),
                "run": run["id"],
                "number": run["incident"],
                "action": experiment["action"],
            },
        )
        if experiment.get("verdict"):
            for fact in experiment["verdict"]["evidence_ids"]:
                self.q(
                    "MATCH (e:Experiment {id:$experiment}) MERGE (f:Evidence {id:$id}) SET f.reference=$reference,f.graph=$graph MERGE (e)-[:SUPPORTED_BY]->(f)",
                    {
                        "experiment": id_,
                        "id": f"{id_}:{fact}",
                        "reference": fact,
                        "graph": experiment["graph"],
                    },
                )
            for index, sample in enumerate(experiment["observations"]):
                self.q(
                    "MATCH (e:Experiment {id:$experiment}) MERGE (o:Observation {id:$id}) SET o.payload=$payload MERGE (e)-[:OBSERVED]->(o)",
                    {
                        "experiment": id_,
                        "id": f"{id_}_{index}",
                        "payload": json.dumps(sample),
                    },
                )

    def experiments(self, run):
        rows = self.q(
            "MATCH (e:Experiment {run_id:$run,incident_number:$number}) RETURN e.payload ORDER BY e.action",
            {"run": run["id"], "number": run["incident"]},
        )
        return [json.loads(row[0]) for row in rows]

    def save_snapshot(self, run, bundle, graph):
        self.q(
            "MERGE (s:Snapshot {id:$id}) SET s.payload=$payload,s.graph=$graph,s.version=$version",
            {
                "id": f"{run['id']}_{run['incident']}",
                "payload": json.dumps(bundle),
                "graph": graph,
                "version": run["version"],
            },
        )

    def snapshot(self, run):
        rows = self.q(
            "MATCH (s:Snapshot {id:$id}) RETURN s.payload,s.graph,s.version",
            {"id": f"{run['id']}_{run['incident']}"},
        )
        return (json.loads(rows[0][0]), rows[0][1], rows[0][2]) if rows else None

    def reserve_application(self, run, key, action):
        id_ = f"{run['id']}_{run['incident']}"
        self.q(
            "MERGE (a:Application {id:$id}) ON CREATE SET a.key=$key,a.status='pending',a.action=$action",
            {"id": id_, "key": key, "action": action},
        )
        row = self.q(
            "MATCH (a:Application {id:$id}) RETURN a.key,a.status,a.action", {"id": id_}
        )[0]
        return {"key": row[0], "status": row[1], "action": row[2]}

    def applied(self, run):
        self.q(
            "MATCH (a:Application {id:$id}) SET a.status='done'",
            {"id": f"{run['id']}_{run['incident']}"},
        )

    def drop_graph(self, name):
        self.require_graph(name)
        if name in self.db.list_graphs():
            self.db.select_graph(name).delete()

    def reset_run(self, run):
        run["status"] = "archived"
        self.save(run)
        self.q(
            "MATCH (c:Control {id:'singleton'}) WHERE c.active_run=$id SET c.active_run=''",
            {"id": run["id"]},
        )
