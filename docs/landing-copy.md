# Landing page copy (`apps/web/src/app/page.tsx`)

Direct from SPEC §11.1 — preserved here so designers can iterate without
touching the React components.

## Hero (above the fold)

> # The research workspace for AI agents.
>
> Margin gives your agents persistent, typed, citation-backed state across
> sessions and models. Connect over MCP or REST. Eight primitives. Free for
> solo developers.
>
> **Add to Claude →** `https://api.margin.dev/mcp/<your-key>` _(copy)_
>
> ```bash
> curl -X POST https://api.margin.dev/v1/projects \
>   -H "Authorization: Bearer $MARGIN_KEY" \
>   -d '{"topic":"free-tier MCP hosting","depth":"thorough"}'
> # → { "project_id": "p_K1aZ9b...", "dashboard_url": "..." }
> ```
>
> [Watch a 90-second demo →] [Read the docs →] [GitHub →]

## Below the fold

### What agents get
Eight primitives, each with a one-line purpose and a copyable example.
(See `apps/web/src/components/PrimitivesTable.tsx`.)

### State that survives the model
A 200-word explainer with a diagram: **agent A** in Claude → finding `f1` →
**agent B** in Cursor next week → `query_findings` → `f1` returns. Same
workspace, different model.

### Built for the RFS
Quote block from Aaron Epstein's "Software for Agents" RFS, followed by
"Margin is the picks-and-shovels."
