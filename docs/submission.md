# AFTERSHOCK

**Tagline:** Agents that test three futures before choosing a repair.

**Tracks:** Agents That Act on Connected Data; Agent Memory and Coordination; Company Brain.

## Problem

An incident fix can create a second outage. AI agents need connected operational context and evidence from execution to distinguish a locally plausible repair from a repair that keeps the company working.

## What we built

AFTERSHOCK investigates a failing commerce application, copies its FalkorDB context into three experiment graphs, and tests competing interventions against isolated copies of the working services. It rejects schema-incompatible rollbacks and repairs that interrupt billing, applies the verified fallback, and remembers the observed outcome. A changed company policy invalidates the remembered fix on the next incident.

Agents discover actual MCP tools to follow dependency paths, retrieve source documents with hybrid search, inspect company ownership and decisions, and discover repairs from connected runbooks. Successful recoveries become procedures with graph-backed preconditions. On recurrence, a superseding owner-approved project decision blocks the old repair and produces an internal handoff to the responsible owner.

A decision comparison shows exactly which graph facts changed between the measured recovery and current requirements. Deployment lineage traces rollback incompatibility to an approved release and schema migration. Two tenant memory scopes preserve separate experience, with a focused eight-worker check of reads/writes, exclusive claims, lease recovery, and handoffs.

## Why FalkorDB is essential

Cypher traces dependencies into workflows and customer groups, verifies schema compatibility, and checks sourced policy decisions. Native BFS and shortest paths expose connected context. Full-text and native vector indexes retrieve documents and typed memory using real embeddings. `GRAPH.COPY` provides independent experiment contexts. A separate graph stores task leases, handoffs, evidence, observations, episodic outcomes, semantic preconditions, learned procedures, and public agent dialogue. Without FalkorDB, the controller cannot investigate, verify, coordinate, or apply actions.

## Original work and disclosure

The service harness, graph model, orchestration, bounded tools, verification, interface, tests, and documentation were developed for this project with AI coding assistance. The participant must review the implementation and understand its decisions before submitting. Digital-twin incident response is an existing field; our contribution is this working combination and demonstration.

## Submission fields to complete

- Public repository URL: https://github.com/sneaxhuh/aftershock
- Video URL: pending. Record the final upgraded journey when ready; an earlier recording does not show the new MCP and memory features.
- Deployment: complete local Docker setup in [README](../README.md) and [judging setup](deployment.md), as permitted by rule 10. No hosted service is claimed.
- State whether the submitted video uses live Gemini calls or the labeled deterministic rehearsal adapter.
