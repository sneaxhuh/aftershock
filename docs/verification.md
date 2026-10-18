# Verification performed

## Pre-publication verification — October 18, 2026

- Existing acceptance suite: **11 passed in 26.21 seconds**, against a separate Compose project so the operator's active demo remained intact. This covers real process interventions, continuous billing probes, schema rollback rejection, memory/recovery, changed policy, stale snapshots, snapshot integrity, graph isolation, and explicit model waiting states.
- Focused coordination check: **passed in 3.84 seconds** on real FalkorDB. Eight workers persisted 32 scoped messages; eight claimants produced one lease winner; expired-lease recovery, stale-owner rejection, persisted handoffs, and MCP scope enforcement passed.
- Frontend TypeScript and production build: passed.
- Python syntax and undefined-name checks: passed. A broader inherited lint configuration reports existing import/style and broad-exception warnings; those are not represented as a clean lint run.
- Scanned all 130 existing Git-history objects and tracked files for the configured private API key and common credential signatures: no findings. `.env` remains ignored.
- Optional operator login: verified rejection of unauthenticated console/API/assets and incorrect credentials, acceptance of valid credentials, Secure/HttpOnly cookies, foreign-origin rejection, and startup failure for a missing required password. Disposable graphs were removed.
- Public cloud hosting has not been provisioned. The reproducible Compose setup is the submission's deployment path.

## Decision provenance and tenant memory update — October 18, 2026

- Python compilation, the TypeScript/Vite build, and the production Compose build passed.
- A focused check on real FalkorDB ran **eight simultaneous workers**, persisted **32 scoped messages**, and produced **one winning task claim**. A replacement reclaimed the expired lease, the previous owner's completion was rejected, and a fresh store recovered the handoff. Foreign graph/run access and a foreign run supplied to MCP were rejected. The check uses disposable graphs and publishes its measured report to the memory view.
- Two independent signed HTTP sessions returned **404** for foreign run IDs, **401** for a forged session, **403** for a foreign browser origin, and **409** for a parked tenant's runtime operation. Switching to Harbor and back restored Northstar's executable state. Harbor's policy change did not invalidate Northstar's learned procedure.
- A real controller restart preserved Harbor's signed session without issuing a replacement cookie, its active run, and peer-run rejection. Northstar's decision comparison remained readable and its saved changed-policy environment restored afterward. The session-signing state and coordination report survived in FalkorDB.
- A shared-browser two-tab check confirmed that changing the signed workspace in one tab reloads the other tab and clears the previous company's comparison/context. Switching back restored Northstar's decision view.
- A live browser journey switched workspaces, inspected Harbor's separate empty outcome memory, displayed the coordination report and deployment source, and returned to Northstar's verified recovery. Updating Northstar's requirement then created a stale context, disabled unsupported investigation/application, and required a new incident.
- The new changed-policy incident completed with **six model requests** and an unresolved outcome. Its rollback evidence included `deployment-481`. The comparison retained three verified baseline samples, showed dependency/policy/approval changes, identified the invalidated procedure, and displayed the new rejected experiment verdict. Unsupported application returned **409**.
- No JavaScript errors or horizontal overflow were observed at a **390px** viewport. Local QA screenshots were inspected. No new demo video was recorded. This update adds one focused coordination-check command, not a broad new test suite.
- Local aggregate evidence is in `.runtime/tenant-http-smoke.json`, `.runtime/tenant-restart-smoke.json`, and `.runtime/new-features-live-smoke.json`; these files remain outside source control. Local operators can activate both demo workspaces; production identity and role management are not claimed.

## daisyUI redesign

The React console was redesigned using the official daisyUI 5 plugin and Tailwind CSS 4. The TypeScript/Vite build and pinned Docker build passed. See [design references and implementation](ui-design.md).

A focused browser journey used the live local API: policy on/off, fault injection, investigation, three experiment comparisons, rollback evidence review, verified application, and applicable learned memory. The incident resolved using six model requests. No JavaScript errors were observed. Further UI checks confirmed a three-node owner → decision → project focus, a failing checkout v1 in the rollback branch, recovered checkout in the main branch, and no horizontal overflow at 390px viewport width.

Only local layout screenshots were captured for inspection. No demo video or additional automated test files were created. Earlier recordings and screenshots show the previous interface.

## Strengthening update

The upgraded implementation was checked on October 17, 2026, with Python compilation, a TypeScript/Vite production build, and one focused two-incident live journey. No additional automated test suite or new demo recording was added for this update.

- Actual MCP schema discovery and calls covered all seven graph tools.
- Native document vector retrieval and full-text retrieval both returned matches using real `gemini-embedding-001` embeddings. Retrieval reported no degraded provider state.
- The owner → decision → project path returned `maya → decision-42 → checkout-resilience`. Native query inspection showed `Node By Index Scan` for a service ID lookup.
- The first incident used **five generation requests**. Fallback passed with **zero failed billing probes**; the data restart caused **four failed billing probes**; rollback was rejected. These are observations from this local journey, not performance benchmarks.
- Applying the verified recovery created an applicable learned procedure linked to the successful outcome.
- A fresh controller instance read persisted public dialogue and memory. After the sourced mandatory-policy update, the second live incident used **six generation requests**, blocked fallback, returned an unresolved outcome, and assigned an internal escalation to Maya in Commerce engineering. The earlier procedure became inapplicable.
- The journey retained 33 public messages. The local evidence summary is `.runtime/strengthening-smoke.json`, which is excluded from source control.
- The rebuilt default Compose stack started successfully. Its API and homepage responded normally; a fresh company passed checkout and billing probes. A browser smoke check rendered the new source, ownership-path, and memory views without JavaScript errors or mobile horizontal overflow. No screenshot or video was recorded. The exact supplied API key was checked against source files and remains confined to ignored `.env`.

The earlier recording below predates these upgrades and should be replaced when the final demo is recorded. Compilation and the focused live journey do not establish tenant isolation or high-concurrency behavior.

## Original implementation

Verified locally on October 17, 2026, with the production Docker Compose stack, FalkorDB 4.18.0, and live `gemini-3.5-flash-lite` agents.

- **11 automated tests passed**: unit verification rules and real graph/sandbox integration tests, including interrupted-controller handoff recovery, lease reclamation, snapshot corruption rejection, stale snapshots, model budget exhaustion, and changed policy.
- **Both live-agent incidents passed**: four model requests per incident. Gemini called the dependency, evidence, incident-memory, action-proposal, and experiment-result tools.
- **Actual interventions verified**: rollback changed the checkout PID and returned HTTP 409 for schema incompatibility; shared-data restart changed its PID and caused billing failures; fallback restored checkout and left billing healthy.
- **Real controller restart verified in the browser**: after `docker compose restart api`, the previous recovery and stored outcome remained available. The changed-policy investigation retrieved prior experience and rejected bypassing mandatory recommendations.
- **Graph outage verified**: stopping FalkorDB caused health and repair-application endpoints to return HTTP 503. Restarting it restored the active run, evidence, experiments, and outcomes from the mounted append-only persistence volume.
- **Production build passed**: TypeScript, Vite, pinned container bases, and locked Python/npm dependency installation. npm reported zero known vulnerabilities at installation.
- **Browser journey passed**: healthy initialization, incident injection, three experiments, evidence drawer, verified application, memory, restart, and changed-policy refusal. Desktop and mobile layouts were inspected.
- **Secret checks passed**: the supplied API key was moved out of `.env.example` into ignored `.env`; staged source was checked for the exact key. Secrets and runtime artifacts are excluded from Git and Docker build context.

In the recorded changed-policy run, the three experiments shared one snapshot checksum and took approximately 2.3–4.2 seconds each. The shared-data restart produced four failed billing probes. These are observations from one local demonstration, not general performance benchmarks.

The live browser recording is `artifacts/aftershock-live-demo.webm` (approximately 49 seconds, without narration). Screenshots, including evidence and controller-restored memory, are alongside it. The narration outline in `docs/demo-script.md` expands the story to approximately three minutes.

The initial `gemini-3.8-flash` selection repeatedly returned upstream HTTP 504 deadline errors. The responding free Flash-Lite model was verified end to end and made the default. `GEMINI_MODEL` remains configurable.

At the time of the original verification, source was local. The current repository is https://github.com/sneaxhuh/aftershock. Public hosting, an updated video upload, and hackathon submission remain pending.
