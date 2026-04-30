# YC Application — Margin

## Company name (50 chars)
Margin

## One-liner
The research workspace for AI agents.

## What is your company going to make?
Margin is a hosted research workspace whose primary user is an AI agent.
Agents connect via MCP or REST and call eight primitives —
`start_research`, `add_finding`, `cite`, `query_findings`, `branch_project`,
`request_human_review`, `publish_report`, `list_projects` — to build durable,
typed, citation-backed research projects that survive sessions, models, and
human handoffs. The agent does the work; Margin owns the artifact.

## Why now?
Aaron Epstein's Summer 2026 RFS says agents need "APIs, MCPs, and CLIs"
with "thorough documentation" and that "every major category of software
that people use today needs to be rebuilt for agents." The agent-infra
layer below us is funded — Mem0 raised $24M for memory, Zep similar,
Browserbase Series B at $300M, Composio $29M — but **the research
workspace category is empty**. NotebookLM and Claude Projects are clients
for humans. Memory tools store facts, not artifacts. Skills are procedural,
not persistent. The lane is open and MCP adoption (270+ servers in the
Docker MCP Catalog as of February 2026) is the distribution channel.

## Progress
Live at https://margin.dev (target). Built solo in 2 days. Open-source MIT
on GitHub at github.com/ahmedbinaasim/margin. Eight MCP tools and a REST
mirror, deployed on Render + Cloudflare + Neon at $0/mo recurring. Demo
video shows Claude Desktop using Margin across two separate sessions to
research, contradict, branch, review, and publish a report. Real users
will be added in the week of submission.

## How will you make money?
Free for solo developers (one agent, 1k findings, 100MB storage). $20/mo
Pro for ten agents and 100k findings; $200/mo Team adds shared projects and
SSO. Storage is the natural lock-in — Aaron Epstein's pricing rule of
"charge from day one or freemium with clear lock-in" maps directly onto a
research workspace where the artifact's value compounds with use.

## Founder bio impressive line (placeholder)
*(replace with real)* "Built and shipped <thing> with <metric>; previously
<role at credible co>; deepest experience with <relevant stack>."

## Other ideas
- An "MCP gateway" that proxies and rate-limits multiple MCP servers with
  one key, exposing a billing/audit layer.
- An MCP tool registry with semantic search for agents discovering tools at
  runtime.
- A CLI-first agent eval harness that lives next to the workspace.

## Hacker question
*(honest, concrete, non-tech, ~80 words — fill in)*
