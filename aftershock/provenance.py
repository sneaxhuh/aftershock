"""Source-backed deployment lineage and comparisons with immutable incident context."""

import json

DEPLOYMENT_QUERY = """MATCH (d:Deployment)-[deploys:DEPLOYS]->(s:Service {id:'checkout'}),
(d)-[applies:APPLIES]->(m:Migration)-[produces:PRODUCES]->(schema:Schema),
(:Service {id:'data'})-[supports:SUPPORTS]->(schema),
(owner:Person)-[approves:APPROVED]->(d),(d)-[belongs:PART_OF]->(project:Project),
(d)-[cites:CITES]->(doc:Document)
WHERE d.active=true
RETURN d.id,d.name,d.version,m.id,m.name,m.backward_compatible,schema.version,
owner.id,owner.name,project.id,project.name,doc.id,doc.text,doc.source,
[deploys.id,applies.id,produces.id,supports.id,approves.id,belongs.id,cites.id]"""


class Provenance:
    def deployment_context(self, graph):
        rows = self.q(DEPLOYMENT_QUERY, graph=graph)
        return [
            dict(
                id=dep,
                name=name,
                checkout_version=version,
                migration={
                    "id": migration,
                    "name": migration_name,
                    "backward_compatible": compatible,
                },
                schema_version=schema,
                owner={"id": owner, "name": owner_name},
                project={"id": project, "name": project_name},
                document={"id": doc, "text": text, "source": source},
                evidence_ids=[
                    dep,
                    migration,
                    f"schema-v{schema}",
                    owner,
                    project,
                    doc,
                    *edges,
                ],
                query=DEPLOYMENT_QUERY,
            )
            for dep, name, version, migration, migration_name, compatible, schema, owner, owner_name, project, project_name, doc, text, source, edges in rows
        ]

    def requirement_context(self, graph):
        rows = self.q(
            """MATCH (:Service {id:'checkout'})-[dependency:DEPENDS_ON]->(:Service {id:'recommendations'}),
(:Service {id:'checkout'})-[:GOVERNED_BY]->(policy:Policy {id:'policy-recommendations'})
RETURN dependency.id,dependency.required,policy.id,policy.required""",
            graph=graph,
        )
        if not rows:
            raise ValueError("Requirement evidence is unavailable")
        edge, required, policy, policy_required = rows[0]
        decisions = self.company_context(graph)["decisions"]
        return {
            "dependency_id": edge,
            "dependency_required": required,
            "policy_id": policy,
            "policy_required": policy_required,
            "decisions": decisions,
            "prediction": self.predict(graph, "enable_fallback"),
        }

    def decision_diff(self, run):
        rows = self.q("""MATCH (i:Incident)-[:RESULTED_IN]->(o:Outcome)
WHERE o.status='resolved' AND i.action='enable_fallback'
RETURN i.id,i.run_id,o.payload,i.recorded_at ORDER BY i.recorded_at DESC LIMIT 1""")
        if not rows:
            return {
                "available": False,
                "reason": "Apply a verified fallback to establish a measured baseline.",
            }
        incident, run_id, payload, at = rows[0]
        prior = self.get(run_id)
        prior["incident"] = int(incident.rsplit("_", 1)[1])
        snapshot = self.snapshot(prior)
        if not snapshot:
            return {
                "available": False,
                "reason": "The earlier outcome has no frozen incident context.",
            }
        _, graph, version = snapshot
        baseline = self.requirement_context(graph)
        historical = next(
            (
                e
                for e in self.experiments(prior)
                if e["action"] == "enable_fallback"
                and e.get("verdict", {}).get("passed")
            ),
            None,
        )
        if historical:
            # Preserve the actual historical decision, even if verification rules evolve.
            baseline["prediction"] = historical["prediction"]
        current = self.requirement_context(run["company_graph"])
        changes = []
        for field in ("dependency_required", "policy_required"):
            if baseline[field] != current[field]:
                changes.append(
                    {
                        "field": field,
                        "before": baseline[field],
                        "after": current[field],
                        "evidence_id": current["dependency_id"]
                        if field.startswith("dependency")
                        else current["policy_id"],
                    }
                )
        before_ids = sorted({d["id"] for d in baseline["decisions"]})
        after_ids = sorted({d["id"] for d in current["decisions"]})
        if before_ids != after_ids:
            changes.append(
                {
                    "field": "approved_decision",
                    "before": before_ids,
                    "after": after_ids,
                    "evidence_id": after_ids[0] if after_ids else current["policy_id"],
                }
            )
        invalidated = self.q(
            "MATCH (p:Procedure {action:'enable_fallback'}) WHERE p.active=false RETURN p.id,p.invalidated_by,p.revision"
        )
        outcome = json.loads(payload)
        samples = outcome.get("observations", [])
        experiments = self.experiments(run) if run["incident"] else []
        experiment = next(
            (e for e in experiments if e["action"] == "enable_fallback"), None
        )
        current["observed_verdict"] = (
            experiment.get("verdict")
            if experiment and experiment["version"] == run["version"]
            else None
        )
        current["incident"] = f"{run['id']}_{run['incident']}"
        current["version"] = run["version"]
        return {
            "available": True,
            "tenant_id": self.tenant,
            "changed_decision": baseline["prediction"]["eligible"]
            != current["prediction"]["eligible"],
            "baseline": {
                **baseline,
                "incident": incident,
                "version": version,
                "snapshot_graph": graph,
                "recorded_at": at,
                "outcome": outcome["status"],
                "verified_samples": sum(
                    s["checkout"]["ok"] and s["billing"]["ok"] for s in samples
                ),
            },
            "current": current,
            "changes": changes,
            "invalidated_procedures": [
                {"id": id_, "invalidated_by": source, "revision": revision}
                for id_, source, revision in invalidated
            ],
            "evidence_ids": current["prediction"]["evidence_ids"],
        }
