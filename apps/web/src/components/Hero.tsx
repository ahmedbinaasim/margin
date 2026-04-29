import Link from "next/link";
import { CodeBlock } from "./CodeBlock";

export function Hero() {
  return (
    <section className="mx-auto max-w-5xl px-6 pt-24 pb-16">
      <div className="text-xs uppercase tracking-widest text-[#8a8e93]">
        the research workspace for AI agents
      </div>
      <h1 className="mt-3 text-5xl font-semibold leading-[1.05] tracking-tight md:text-6xl">
        Margin gives your agents{" "}
        <span className="text-[#f5dd5b]">durable, citation-backed</span>{" "}
        research that survives the model.
      </h1>
      <p className="mt-6 max-w-2xl text-lg text-[#a9adb1]">
        Eight primitives. MCP and REST. Free for solo developers. Connect Claude
        Desktop with one URL — every claim, citation, branch, and review is
        persisted, queryable, and replayable across sessions and models.
      </p>

      <div className="mt-10 grid gap-6 md:grid-cols-2">
        <div>
          <div className="text-xs uppercase tracking-widest text-[#8a8e93]">
            Add to Claude
          </div>
          <CodeBlock className="mt-2">
            {`https://api.margin.dev/mcp/<your-key>`}
          </CodeBlock>
          <p className="mt-2 text-sm text-[#8a8e93]">
            Settings → Connectors → Add custom connector → paste this URL.{" "}
            <Link href="/app">Get a key →</Link>
          </p>
        </div>
        <div>
          <div className="text-xs uppercase tracking-widest text-[#8a8e93]">
            Or call REST
          </div>
          <CodeBlock className="mt-2">
            {`curl -X POST https://api.margin.dev/v1/projects \\
  -H "Authorization: Bearer $MARGIN_KEY" \\
  -d '{"topic":"free-tier MCP hosting","depth":"thorough"}'
# → { "project_id": "p_K1aZ9b...", "dashboard_url": "..." }`}
          </CodeBlock>
        </div>
      </div>

      <div className="mt-8 flex gap-4 text-sm">
        <Link
          href="/app"
          className="rounded-md border border-[#1f2227] bg-[#131619] px-4 py-2 hover:bg-[#1a1d22]"
        >
          Get a key
        </Link>
        <Link
          href="/docs"
          className="rounded-md border border-[#1f2227] px-4 py-2 hover:bg-[#131619]"
        >
          Docs
        </Link>
        <a
          href="https://github.com/ahmedbinaasim/margin"
          className="rounded-md border border-[#1f2227] px-4 py-2 hover:bg-[#131619]"
        >
          GitHub
        </a>
      </div>
    </section>
  );
}
