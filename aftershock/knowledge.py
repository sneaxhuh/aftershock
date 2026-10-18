"""Connected company knowledge, native retrieval and reusable incident experience."""

import hashlib
import json
import re
import time
import uuid
from aftershock.domain import Action

BFS_QUERY = """MATCH (s:Service {id:$service})
CALL algo.bfs(s,4,'DEPENDS_ON') YIELD nodes,edges
RETURN [n IN nodes | n.id],[r IN edges | r.id]"""
SHORTEST_QUERY = """MATCH (a {id:$source}),(b {id:$target})
WITH shortestPath((a)-[*1..8]->(b)) AS p
RETURN [n IN nodes(p) | n.id],[r IN relationships(p) | r.id]"""
DISCOVERY_QUERY = """MATCH (s:Service {id:'checkout'})<-[:DOCUMENTS]-(d:Document)
-[suggestion:SUGGESTS]->(r:Repair)-[:TARGETS]->(target:Service)
WHERE r.enabled=true
RETURN DISTINCT r.action,r.name,d.id,target.id,suggestion.id"""


class Knowledge:
    def create_index(self, query, graph=None):
        try:
            self.q(query, graph=graph)
        except Exception as error:
            if "already" not in str(error).lower():
                raise

    def initialize_knowledge(self):
        for label in [
            "Run",
            "Task",
            "Incident",
            "Procedure",
            "EmbeddingCache",
            "MemoryEntry",
        ]:
            self.create_index(f"CREATE INDEX FOR (n:{label}) ON (n.id)")
        self.create_index("CREATE INDEX FOR (n:Message) ON (n.run_id)")
        self.create_index(
            "CREATE VECTOR INDEX FOR (n:MemoryEntry) ON (n.embedding) OPTIONS {dimension:768,similarityFunction:'cosine'}"
        )

    def explain_path(self, graph, source, target):
        rows = self.q(SHORTEST_QUERY, {"source": source, "target": target}, graph)
        return {
            "nodes": (rows[0][0] or []) if rows else [],
            "edges": (rows[0][1] or []) if rows else [],
            "algorithm": "shortestPath",
            "query": SHORTEST_QUERY,
            "meaning": "Shortest evidence connection; not a claim of causality.",
        }

    def company_context(self, graph):
        owners = self.q(
            "MATCH (p:Person)-[o:OWNS]->(s:Service) OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team) RETURN p.id,p.name,s.id,t.name,o.id",
            graph=graph,
        )
        projects = self.q(
            "MATCH (t:Team)-[:LEADS]->(p:Project)-[:INCLUDES]->(s:Service {id:'checkout'}) RETURN p.id,p.name,t.name",
            graph=graph,
        )
        decisions = self.q(
            "MATCH (d:Decision)-[:ESTABLISHES]->(p:Policy {id:'policy-recommendations'}),(person:Person)-[:APPROVED]->(d),(d)-[:CITES]->(source:Document) WHERE d.current=true RETURN d.id,d.name,d.required,person.name,source.id,source.text,source.source",
            graph=graph,
        )
        sources = self.q(
            "MATCH (d:Document)-[:DOCUMENTS]->(:Service {id:'checkout'}) RETURN d.id,d.name,d.kind,d.source,d.text",
            graph=graph,
        )
        waypoint = decisions[0][0] if decisions else None
        owner_id = next((row[0] for row in owners if row[2] == "checkout"), "maya")
        owner_path = (
            self.explain_path(graph, owner_id, waypoint)
            if waypoint
            else {"nodes": [], "edges": [], "algorithm": "shortestPath"}
        )
        if waypoint:
            tail = self.explain_path(graph, waypoint, "checkout-resilience")
            owner_path["nodes"] += tail["nodes"][1:]
            owner_path["edges"] += tail["edges"]
            owner_path["waypoint"] = waypoint
        return {
            "owners": [
                {
                    "id": id_,
                    "name": name,
                    "service": service,
                    "team": team,
                    "evidence_id": evidence,
                }
                for id_, name, service, team, evidence in owners
            ],
            "projects": [
                {"id": id_, "name": name, "team": team} for id_, name, team in projects
            ],
            "decisions": [
                {
                    "id": id_,
                    "name": name,
                    "required": required,
                    "approved_by": person,
                    "source_id": source,
                    "text": text,
                    "source": reference,
                }
                for id_, name, required, person, source, text, reference in decisions
            ],
            "sources": [
                {
                    "id": id_,
                    "name": name,
                    "kind": kind or "runbook",
                    "source": source,
                    "text": text,
                    "current_decision_source": any(row[4] == id_ for row in decisions),
                }
                for id_, name, kind, source, text in sources
            ],
            "owner_path": owner_path,
            "deployments": self.deployment_context(graph),
        }

    def discover_repairs(self, graph):
        rows = self.q(DISCOVERY_QUERY, graph=graph)
        learned = {p["action"]: p for p in self.procedures(graph)}
        result = []
        for action, name, document, target, edge in rows:
            if action not in {a.value for a in Action}:
                continue
            prediction = self.predict(graph, action)
            procedure = learned.get(action)
            result.append(
                {
                    "action": action,
                    "name": name,
                    "source_id": document,
                    "target": target,
                    "evidence_ids": [edge, *prediction["evidence_ids"]],
                    "prediction": prediction,
                    "learned_procedure": procedure,
                    "query": DISCOVERY_QUERY,
                }
            )
        result.sort(
            key=lambda r: (
                not bool(
                    r["learned_procedure"] and r["learned_procedure"]["applicable"]
                ),
                not r["prediction"]["eligible"],
                r["action"],
            )
        )
        return result

    def procedures(self, graph):
        rows = self.q(
            "MATCH (p:Procedure) RETURN p.id,p.action,p.text,p.confirmed_runs,p.active,p.invalidated_at,p.revision ORDER BY p.updated_at DESC LIMIT 12"
        )
        result = []
        for id_, action, text, count, active, invalidated, revision in rows:
            prediction = self.predict(graph, action)
            result.append(
                {
                    "id": id_,
                    "action": action,
                    "text": text,
                    "confirmed_runs": count,
                    "applicable": bool(active and prediction["eligible"]),
                    "revision": revision,
                    "invalidated_at": invalidated,
                    "current_reason": prediction["reason"],
                    "evidence_ids": prediction["evidence_ids"],
                    "memory_type": "procedural",
                }
            )
        return result

    def learn_procedure(self, run, outcome):
        if outcome.get("status") != "resolved":
            return
        samples = outcome.get("observations", [])
        if len(samples) < 3 or not all(
            s["checkout"]["ok"] and s["billing"]["ok"] for s in samples[-3:]
        ):
            return
        action = outcome["action"]
        incident = f"{run['id']}_{run['incident']}"
        id_ = f"procedure:{action}:required:{run['required']}"
        text = (
            f"Verified procedure for checkout recommendations timeout: {action}. "
            f"Recommendations required={run['required']}. Verify graph compatibility and policy, "
            "test in an isolated snapshot, and require three successful checkout and billing probes before reuse."
        )
        self.q(
            """MATCH (o:Outcome {id:$incident}) MERGE (p:Procedure {id:$id})
ON CREATE SET p.action=$action,p.revision=0
SET p.text=$text,p.active=true,p.updated_at=$at,p.revision=p.revision+1
MERGE (p)-[:LEARNED_FROM]->(o)
MERGE (condition:SemanticFact {id:$condition}) SET condition.required=$required
MERGE (p)-[:REQUIRES]->(condition)
WITH p MATCH (p)-[:LEARNED_FROM]->(o:Outcome)
WITH p,count(o) AS confirmations SET p.confirmed_runs=confirmations""",
            {
                "incident": incident,
                "id": id_,
                "action": action,
                "text": text,
                "at": time.time(),
                "condition": f"recommendations-required:{run['required']}",
                "required": run["required"],
            },
        )
        self.memory_entry(id_, "procedural", text, id_)

    def memory_entry(self, id_, kind, text, reference):
        self.q(
            "MERGE (m:MemoryEntry {id:$id}) SET m.kind=$kind,m.text=$text,m.reference=$reference,m.updated_at=$at",
            {
                "id": id_,
                "kind": kind,
                "text": text,
                "reference": reference,
                "at": time.time(),
            },
        )
        self.embeddings.index(self.memory_name, "MemoryEntry", id_, text)

    def hybrid_evidence(self, graph, query="checkout recommendations timeout"):
        words = re.findall(r"[a-zA-Z0-9_]{2,30}", query)[:12]
        lexical = " | ".join(words) or "checkout"
        rows = self.q(
            "CALL db.idx.fulltext.queryNodes('Document',$query) YIELD node,score RETURN node.id,node.name,node.text,node.source,score",
            {"query": lexical},
            graph,
        )
        results = {
            id_: {
                "id": id_,
                "name": name,
                "text": text,
                "source": source,
                "channels": ["fulltext"],
                "score": float(score),
            }
            for id_, name, text, source, score in rows
        }
        if self.embeddings.enabled:
            docs = self.q("MATCH (d:Document) RETURN d.id,d.text", graph=graph)
            for id_, text in docs:
                if text:
                    self.embeddings.index(graph, "Document", id_, text)
            vector = self.embeddings.encode(query, "RETRIEVAL_QUERY")
            if vector is not None:
                hits = self.q(
                    "CALL db.idx.vector.queryNodes('Document','embedding',8,vecf32($vector)) YIELD node,score WHERE node.embedding_model=$model RETURN node.id,node.name,node.text,node.source,score",
                    {"vector": vector, "model": self.embeddings.model},
                    graph,
                )
                for id_, name, text, source, score in hits:
                    entry = results.setdefault(
                        id_,
                        {
                            "id": id_,
                            "name": name,
                            "text": text,
                            "source": source,
                            "channels": [],
                            "score": 0,
                        },
                    )
                    entry["channels"].append("vector")
                    # FalkorDB 4.18 returns cosine distance: 0 is an exact match.
                    entry["distance"] = float(score)
                    entry["similarity"] = 1.0 - float(score)
        ranked = sorted(
            results.values(),
            key=lambda item: (
                len(item["channels"]),
                item.get("similarity", 0),
                item["score"],
            ),
            reverse=True,
        )[:8]
        return {
            "sources": ranked,
            "retrieval": {
                "fulltext": True,
                "vector": any("vector" in d["channels"] for d in ranked),
                "degraded_reason": self.embeddings.error,
            },
            "company": self.company_context(graph),
        }

    def semantic_memories(self, query):
        vector = self.embeddings.encode(query, "RETRIEVAL_QUERY")
        if vector is None:
            return {"matches": [], "available": False, "reason": self.embeddings.error}
        hits = self.q(
            "CALL db.idx.vector.queryNodes('MemoryEntry','embedding',8,vecf32($vector)) YIELD node,score WHERE node.embedding_model=$model RETURN node.id,node.kind,node.text,node.reference,score",
            {"vector": vector, "model": self.embeddings.model},
        )
        return {
            "available": True,
            "matches": [
                {
                    "id": id_,
                    "memory_type": kind,
                    "text": text,
                    "reference": reference,
                    "similarity": 1.0 - float(score),
                    "distance": float(score),
                }
                for id_, kind, text, reference, score in hits
            ],
        }

    def record_policy_decision(self, graph, required):
        stamp = uuid.uuid4().hex[:10]
        decision, source = f"decision-{stamp}", f"policy-source-{stamp}"
        text = f"Maya, Commerce service owner: recommendations are {'mandatory; graceful fallback is prohibited' if required else 'optional; verified graceful fallback is permitted'}. This supersedes the earlier policy decision."
        rows = self.q(
            """MATCH (p:Policy {id:'policy-recommendations'}),(owner:Person {id:'maya'}),(project:Project {id:'checkout-resilience'}),(service:Service {id:'checkout'})
MATCH (old:Decision)-[:ESTABLISHES]->(p) WHERE old.current=true
SET old.current=false
CREATE (d:Decision {id:$id,name:$name,current:true,required:$required,created_at:$at,source:$source,x:900,y:-80})
CREATE (doc:Document {id:$doc,name:'Company policy update',kind:'chat',text:$text,source:$source,x:900,y:-240})
CREATE (d)-[:ESTABLISHES {id:$establishes,source:$source}]->(p),(owner)-[:APPROVED {id:$approves,source:$source}]->(d),
(d)-[:CITES {id:$cites,source:$source}]->(doc),(d)-[:AFFECTS {id:$affects,source:$source}]->(project),(d)-[:SUPERSEDES {id:$supersedes,source:$source}]->(old),
(doc)-[:DOCUMENTS {id:$documents,source:$source}]->(service)
RETURN d.id""",
            {
                "id": decision,
                "doc": source,
                "name": "Mandatory recommendations"
                if required
                else "Optional recommendations",
                "required": required,
                "at": time.time(),
                "text": text,
                "source": f"policy-update:{stamp}",
                "establishes": f"{decision}:ESTABLISHES:policy-recommendations",
                "approves": f"maya:APPROVED:{decision}",
                "cites": f"{decision}:CITES:{source}",
                "affects": f"{decision}:AFFECTS:checkout-resilience",
                "supersedes": f"{decision}:SUPERSEDES:previous",
                "documents": f"{source}:DOCUMENTS:checkout",
            },
            graph,
        )
        if not rows:
            raise ValueError("No current sourced policy decision to supersede")
        if required:
            self.q(
                "MATCH (p:Procedure {action:'enable_fallback'}) SET p.active=false,p.invalidated_at=$at,p.invalidated_by=$source",
                {"at": time.time(), "source": decision},
            )
        return decision

    def message(self, run, role, kind, content):
        # Preserve public dialogue and tool I/O, excluding model thought/signature fields.
        if isinstance(content, dict) and "parts" in content:
            content = {
                **content,
                "parts": [
                    {
                        k: v
                        for k, v in part.items()
                        if k not in ("thought_signature", "thought")
                    }
                    for part in content["parts"]
                    if not part.get("thought")
                ],
            }
        self.q(
            """MATCH (c:Control {id:'singleton'}),(r:Run {id:$run})
SET c.message_sequence=coalesce(c.message_sequence,0)+1
CREATE (m:Message {id:$id,run_id:$run,incident:$incident,role:$role,kind:$kind,sequence:c.message_sequence,at:$at,payload:$payload})
CREATE (r)-[:HAS_MESSAGE]->(m)""",
            {
                "id": uuid.uuid4().hex,
                "run": run["id"],
                "incident": run["incident"],
                "role": role,
                "kind": kind,
                "at": time.time(),
                "payload": json.dumps(content),
            },
        )

    def conversation(self, run_id):
        rows = self.q(
            "MATCH (m:Message {run_id:$run}) RETURN m.sequence,m.role,m.kind,m.incident,m.at,m.payload ORDER BY m.sequence DESC LIMIT 100",
            {"run": run_id},
        )
        return [
            {
                "sequence": seq,
                "role": role,
                "kind": kind,
                "incident": incident,
                "at": at,
                "content": json.loads(payload),
            }
            for seq, role, kind, incident, at, payload in reversed(rows)
        ]

    def record_decisions(self, run, experiments, selected):
        incident = f"{run['id']}_{run['incident']}"
        for experiment in experiments:
            decision = f"{incident}:decision:{experiment['action']}"
            self.q(
                """MATCH (i:Incident {id:$incident}),(e:Experiment {id:$experiment})
MERGE (d:Decision {id:$id}) SET d.action=$action,d.selected=$selected,d.reasons=$reasons,d.at=$at
MERGE (i)-[:MADE_DECISION]->(d) MERGE (d)-[:BASED_ON]->(e)""",
                {
                    "incident": incident,
                    "experiment": f"{incident}_{experiment['action']}",
                    "id": decision,
                    "action": experiment["action"],
                    "selected": experiment["action"] == selected,
                    "reasons": experiment["verdict"]["reasons"],
                    "at": time.time(),
                },
            )

    def escalate(self, run):
        context = self.company_context(run["company_graph"])
        owner = next(
            (owner for owner in context["owners"] if owner["service"] == "checkout"),
            None,
        )
        if not owner:
            return None
        id_ = f"{run['id']}_{run['incident']}:escalation"
        self.q(
            """MATCH (i:Incident {id:$incident})
MERGE (p:PersonRef {id:$owner}) SET p.name=$name,p.team=$team
MERGE (e:Escalation {id:$id}) SET e.status='open',e.reason=$reason,e.created_at=$at
MERGE (i)-[:ESCALATED_AS]->(e) MERGE (e)-[:ASSIGNED_TO]->(p)""",
            {
                "incident": f"{run['id']}_{run['incident']}",
                "owner": owner["id"],
                "name": owner["name"],
                "team": owner["team"],
                "id": id_,
                "reason": "No verified repair satisfies current company requirements.",
                "at": time.time(),
            },
        )
        return {
            "id": id_,
            "owner": owner,
            "status": "open",
            "decision_ids": sorted({d["id"] for d in context["decisions"]}),
        }

    def graph_insights(self, graph):
        query = "MATCH (s:Service {id:$id}) RETURN s.id"
        plan = self.db.select_graph(graph).explain(query, {"id": "checkout"})
        return {
            "query": query,
            "plan": "\n".join(plan) if isinstance(plan, list) else str(plan),
            "features": [
                "range indexes",
                "fulltext search",
                "vector indexes",
                "algo.bfs",
                "shortestPath",
                "GRAPH.COPY",
            ],
        }
