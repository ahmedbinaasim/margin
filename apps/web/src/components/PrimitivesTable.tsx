const rows: { name: string; signature: string; purpose: string }[] = [
  {
    name: "start_research",
    signature: "(topic, depth?, deadline?)",
    purpose: "Begin a research project.",
  },
  {
    name: "add_finding",
    signature: "(project_id, claim, evidence, confidence, source?, contradicts?)",
    purpose: "Record a typed claim with evidence. Idempotent on (project, hash).",
  },
  {
    name: "cite",
    signature: "(finding_id, url, excerpt)",
    purpose:
      "Attach a citation; the server fetches, extracts, hashes, archives.",
  },
  {
    name: "query_findings",
    signature: "(project_id, semantic_query, limit?, min_confidence?)",
    purpose: "Semantic recall over prior findings via Voyage embeddings.",
  },
  {
    name: "branch_project",
    signature: "(project_id, reason)",
    purpose: "Fork into a sub-investigation; parent stays intact.",
  },
  {
    name: "request_human_review",
    signature: "(project_id, reason)",
    purpose: "Pause for human approval. Surfaces on the dashboard.",
  },
  {
    name: "publish_report",
    signature: "(project_id, format?)",
    purpose: "Render a citation-backed report at a stable public URL.",
  },
  {
    name: "list_projects",
    signature: "(limit?, status?)",
    purpose: "List the calling agent's projects, most recent first.",
  },
];

export function PrimitivesTable() {
  return (
    <section className="mx-auto max-w-5xl px-6 py-16">
      <h2 className="text-2xl font-semibold tracking-tight">
        The eight primitives
      </h2>
      <p className="mt-2 text-[#8a8e93]">
        Both MCP tools and REST endpoints; same business logic behind each.
      </p>
      <div className="mt-6 overflow-x-auto rounded-md border border-[#1f2227]">
        <table className="w-full text-left text-sm">
          <thead className="bg-[#131619] text-[#a9adb1]">
            <tr>
              <th className="px-4 py-3">Tool</th>
              <th className="px-4 py-3">Signature</th>
              <th className="px-4 py-3">Purpose</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr
                key={r.name}
                className={i % 2 ? "bg-[#0e1115]" : "bg-[#0b0d10]"}
              >
                <td className="px-4 py-3 font-mono text-[#f5dd5b]">{r.name}</td>
                <td className="px-4 py-3 font-mono text-xs text-[#a9adb1]">
                  {r.signature}
                </td>
                <td className="px-4 py-3 text-[#a9adb1]">{r.purpose}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
