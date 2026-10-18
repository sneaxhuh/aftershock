# Demo recording script

Target: approximately three minutes. Keep the rehearsal/live label visible. The recording script exercises real HTTP services and FalkorDB in whichever agent mode the application is running. Live recordings use Gemini function calls; rehearsal recordings explicitly disclose the deterministic adapter.

| Time | Show | Say |
| --- | --- | --- |
| 0:00–0:20 | Healthy company and live requests | “A repair can restore checkout and still break the company. AFTERSHOCK tests the consequences first.” |
| 0:20–0:40 | Inject fault, start investigation | “Recommendations time out. Our investigator retrieves dependencies, runbooks, and previous outcomes from FalkorDB.” |
| 0:40–1:10 | Three futures | “We freeze one application snapshot and fork its graph into three isolated working environments.” |
| 1:10–1:35 | Restart evidence and process IDs | “The data restart actually interrupts billing. The rollback actually runs v1, which fails the schema check. These are HTTP results, not model guesses.” |
| 1:35–1:55 | Apply verified fallback | “Fallback recovers checkout without interrupting billing. The main environment independently verifies the repair.” |
| 1:55–2:15 | Memory, then controller restart | “The verified outcome and role handoffs live in FalkorDB. Restarting the controller does not erase them.” |
| 2:15–2:45 | Mandatory policy, inject again, investigate | “Now recommendations are mandatory. The old repair is remembered, but current evidence disqualifies it. The agent refuses to apply an unsafe remembered fix.” |
| 2:45–3:00 | Evidence paths and unresolved outcome | “Operational context, experiment coordination, and experience are all graph-backed. Every decision has a path.” |

To demonstrate a real controller restart, run `docker compose restart api` between the first recovery and changed-policy incident. For interrupted-task recovery, restart while experiments run; lease reclamation can take up to 90 seconds, so record that separately rather than padding the main video.

To record the live application: start with `AGENT_MODE=live` and a configured key, install development dependencies and Playwright Chromium, then run `RESTART_CONTROLLER=1 python scripts/browser_demo.py`. Artifacts are saved under `artifacts/` and must be reviewed before submission. Rehearsal mode requires no model key and produces a separately named recording.
