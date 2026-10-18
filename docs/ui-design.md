# Incident workspace design

The console uses the official daisyUI 5 Tailwind plugin, Tailwind CSS 4, and the Vite integration. Versions are pinned in `web/package.json` and `web/package-lock.json`. The `aftershock` daisyUI theme defines charcoal surfaces, a sand accent, and semantic success/error colors. Buttons, badges, branch selectors, policy switches, menus, modal surfaces, and evidence tables use daisyUI components.

## References

- [Pinterest: Server Monitoring Dashboard, Dark Version](https://www.pinterest.com/pin/702983823073939887/) — a persistent sidebar, clear operational sections, and status colors reserved for actual signals. The public reference image was inspected during design; none of its imagery is included in the app.
- [Linear: A calmer interface for a product in motion](https://linear.app/now/behind-the-latest-design-refresh) — subdued navigation, consistent action placement, and clear hierarchy in a dense engineering tool.
- [daisyUI: Vite installation](https://daisyui.com/docs/install/vite/) and [custom themes](https://daisyui.com/docs/themes/) — the implementation follows the official plugin setup and supplies a custom theme.

## Layout and behavior

The main screen starts with the current incident and its actions. Live checkout/billing status and experiment progress provide a compact overview. The dependency graph and agent activity sit together, followed by repair comparisons and supporting company context. Company facts and raw dialogue remain inspectable without dominating the incident workspace.

Repair cards show graph-derived eligibility reasons before execution and real HTTP outcomes afterward. Evidence opens in a labeled drawer with source IDs, Cypher, snapshot provenance, probe samples, and process changes. The graph can expand, switch branches, show all context, and focus on a selected evidence path without unrelated nodes. The policy switch updates the actual company requirement and indicates a pending request while it saves.

On narrower screens, navigation contracts to an icon rail; graph and activity stack, and comparison cards become a single column. Keyboard focus remains visible, dialogs close with Escape, and reduced-motion preferences are respected. Local layout screenshots are QA artifacts, not a recorded demonstration.
