# Demo scripts

From SPEC §10. Recording is the user's job — the scripts here are the voice-over.

## 10.1 Product demo (90 s, on the landing page)

**Setup before recording.**
- Two Claude.ai conversations queued.
- A blank Margin dashboard tab open at `https://margin.dev/app`.
- An agent key already minted; copied to clipboard.
- Connector URL pre-pasted in Claude.ai → Settings → Connectors.

**Voice-over (over screen capture):**

> "This is Margin. It's a research workspace where the user is an AI agent.
>
> [0:08] I install it in Claude with one URL — paste, save. Eight tools show up.
>
> [0:15] I say: research the state of free MCP hosting in April 2026. Claude
> calls `start_research`. The dashboard, on the right, shows it live.
>
> [0:30] Claude browses, then calls `add_finding` ten times — each one a typed
> claim, evidence, source, and confidence. Margin embeds each finding into
> pgvector and archives the source HTML to R2 keyed by content hash.
>
> [0:50] I close the chat. I open a brand-new Claude conversation. I say:
> continue the MCP research and find contradictions. Claude calls
> `list_projects`, then `query_findings` with `cold start times`. It pulls
> the relevant findings back from yesterday — semantically.
>
> [1:10] It finds two sources that disagree on Render's cold-start time. It
> calls `branch_project` to fork an investigation, resolves the
> contradiction, then `request_human_review`.
>
> [1:25] I approve. It calls `publish_report`. Here is the report — markdown,
> every claim cited, every source archived, a stable public URL.
>
> [1:30] Margin is the workspace. The agent did the work. The state outlived
> the model."

## 10.2 Founders' video (60 s, for the YC application form)

Per Aaron Epstein: founder on camera, smile, single take, no editing.

> "Hi YC, I'm <name>. I'm building Margin: a research workspace whose
> primary user is an AI agent.
>
> Aaron's RFS says: agents need APIs, MCPs, and CLIs, and every category
> of software needs to be rebuilt for them. The category I'm rebuilding is
> the research workspace — the Notion page or Jupyter notebook of the
> agent era.
>
> Today, agents do research and then forget it the moment the chat ends.
> Memory tools like Mem0 and Zep store facts. Browsers like Browserbase
> give agents a body. Nobody owns the artifact — the structured,
> citation-backed, queryable document the agent produces and hands off
> across sessions.
>
> Margin does. Eight primitives, MCP and REST, free tier from day one,
> paid the moment a team needs to share. I built the MVP solo over a
> weekend; it's live at margin.dev right now and Claude can use it end to
> end.
>
> I'd love to come build this in Summer 2026. Thanks."
