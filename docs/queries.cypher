// Dependencies: source service to reachable dependencies.
MATCH p=(s:Service {id:$service})-[:DEPENDS_ON*1..4]->(d:Service)
RETURN [n IN nodes(p) | n.id], [r IN relationships(p) | r.id];

// Predicted business impact: incoming service dependencies, then business context.
MATCH p=(s:Service)-[:DEPENDS_ON*0..4]->(target:Service {id:$target}),
      (s)-[:SUPPORTS]->(w:Workflow)-[:USED_BY]->(c:CustomerGroup)
RETURN DISTINCT s.id,w.id,c.id,[r IN relationships(p) | r.id];

// Compatibility: compare an actual graph requirement with supported schema.
MATCH (:Service {id:'checkout'})-[r:REQUIRES_SCHEMA {checkout_version:1}]->(needed:Schema),
      (:Service {id:'data'})-[s:SUPPORTS]->(actual:Schema)
RETURN needed.version,actual.version,r.id,s.id;

// Policy: dependency AND governing policy must allow bypass.
MATCH (:Service {id:'checkout'})-[d:DEPENDS_ON]->(:Service {id:'recommendations'}),
      (:Service {id:'checkout'})-[g:GOVERNED_BY]->(p:Policy)
RETURN d.required,p.required,d.id,g.id,p.id;

// Persisted experience retrieval (memory graph).
CALL db.idx.fulltext.queryNodes('Incident','checkout recommendations') YIELD node
RETURN node.id,node.action,node.outcome ORDER BY node.recorded_at DESC LIMIT 5;

// Exclusive, renewable task lease (memory graph).
MATCH (t:Task {id:$id})
WHERE t.status<>'done' AND (t.lease<$now OR t.owner=$owner)
SET t.owner=$owner,t.lease=$until,t.status='running'
RETURN t.id;

// Run GRAPH.COPY <incident_snapshot> <candidate_graph> through the official client.

// Native breadth-first traversal of operational dependencies.
MATCH (s:Service {id:$service})
CALL algo.bfs(s,4,'DEPENDS_ON') YIELD nodes,edges
RETURN [n IN nodes | n.id],[r IN edges | r.id];

// Candidate discovery: changing connected runbooks changes the available repair set.
MATCH (:Service {id:'checkout'})<-[:DOCUMENTS]-(d:Document)
      -[suggestion:SUGGESTS]->(r:Repair)-[:TARGETS]->(target:Service)
WHERE r.enabled=true
RETURN DISTINCT r.action,r.name,d.id,target.id,suggestion.id;

// Current authority: an owner-approved, sourced decision affecting this project.
MATCH (owner:Person)-[:OWNS]->(:Service {id:'checkout'}),
      (owner)-[:APPROVED]->(d:Decision)-[:AFFECTS]->(project:Project)
      -[:INCLUDES]->(:Service {id:'checkout'}),
      (d)-[:ESTABLISHES]->(:Policy {id:'policy-recommendations'}),
      (d)-[:CITES]->(source:Document)
WHERE d.current=true
RETURN d.id,d.required,source.id,owner.id,project.id;

// Native directed shortest evidence path. In FalkorDB, use WITH or RETURN.
MATCH (a {id:$source}),(b {id:$target})
WITH shortestPath((a)-[*1..8]->(b)) AS p
RETURN [n IN nodes(p) | n.id],[r IN relationships(p) | r.id];

// Real embeddings, indexed and queried in FalkorDB (company graph).
CREATE VECTOR INDEX FOR (d:Document) ON (d.embedding)
OPTIONS {dimension:768,similarityFunction:'cosine'};

CALL db.idx.vector.queryNodes('Document','embedding',8,vecf32($vector))
YIELD node,score WHERE node.embedding_model=$model
RETURN node.id,node.text,node.source,score;
// score is cosine distance on the pinned version; similarity = 1 - score.

// Learned procedure provenance and preconditions (memory graph).
MATCH (p:Procedure)-[:LEARNED_FROM]->(o:Outcome),
      (p)-[:REQUIRES]->(condition:SemanticFact)
RETURN p.id,p.action,p.active,condition.required,o.id;

// Evidence for a selection or rejection (memory graph).
MATCH (:Incident {id:$incident})-[:MADE_DECISION]->(d:Decision)
      -[:BASED_ON]->(e:Experiment)
RETURN d.action,d.selected,d.reasons,e.id;

// Stable entity lookup using a native range index.
CREATE INDEX FOR (s:Service) ON (s.id);
MATCH (s:Service {id:$id}) RETURN s.id;

// Current deployment explains the migration behind rollback incompatibility.
MATCH (d:Deployment)-[:DEPLOYS]->(:Service {id:'checkout'}),
      (d)-[:APPLIES]->(m:Migration)-[:PRODUCES]->(schema:Schema),
      (:Service {id:'data'})-[:SUPPORTS]->(schema),
      (owner:Person)-[:APPROVED]->(d),(d)-[:PART_OF]->(project:Project),
      (d)-[:CITES]->(source:Document)
WHERE d.active=true
RETURN d.id,m.id,m.backward_compatible,schema.version,owner.name,project.name,source.source;

// Prior verified baseline, queried only in the bound tenant memory graph.
MATCH (i:Incident)-[:RESULTED_IN]->(o:Outcome)
WHERE o.status='resolved' AND i.action='enable_fallback'
RETURN i.id,i.run_id,o.payload,i.recorded_at ORDER BY i.recorded_at DESC LIMIT 1;
