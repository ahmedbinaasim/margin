import { Hero } from "@/components/Hero";
import { PrimitivesTable } from "@/components/PrimitivesTable";

export default function Home() {
  return (
    <main>
      <Hero />
      <PrimitivesTable />

      <section className="mx-auto max-w-5xl px-6 py-16">
        <h2 className="text-2xl font-semibold tracking-tight">
          State that survives the model
        </h2>
        <p className="mt-3 max-w-3xl text-[#a9adb1]">
          Memory tools store facts. Browsers give agents a body. Sandboxes give
          them hands. Margin is the <em>workspace</em> — the durable, structured
          artifact the agent produces and hands off across sessions, models,
          and human reviewers. An agent in Claude on Monday can hand a project
          to an agent in Cursor on Friday; <code>query_findings</code> returns
          the same vectors regardless of who wrote them.
        </p>
      </section>

      <footer className="mx-auto max-w-5xl px-6 py-12 text-sm text-[#8a8e93]">
        <div className="border-t border-[#1f2227] pt-8">
          MIT licensed ·{" "}
          <a href="https://github.com/ahmedbinaasim/margin">GitHub</a> ·{" "}
          <a href="/docs">Docs</a> ·{" "}
          <a href="/app">Get a key</a>
        </div>
      </footer>
    </main>
  );
}
