"use client";

import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";

type ProjectDetail = {
  project_id: string;
  topic: string;
  depth: string;
  status: string;
  parent_id: string | null;
  created_at: string;
  updated_at: string;
};

type Finding = {
  finding_id: string;
  claim: string;
  evidence: string;
  source_url: string | null;
  confidence: number;
  contradicts: string | null;
  created_at: string;
};

export function ProjectClient({ projectId: initialId }: { projectId: string }) {
  const [projectId, setProjectId] = useState(initialId);
  const [agentKey, setAgentKey] = useState<string | null>(null);
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [findings] = useState<Finding[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setAgentKey(localStorage.getItem("margin.agent_key"));
    if (typeof window !== "undefined") {
      const m = window.location.pathname.match(/^\/app\/p\/([^/]+)/);
      if (m && m[1] && m[1] !== "shell") setProjectId(decodeURIComponent(m[1]));
    }
  }, []);

  useEffect(() => {
    if (!projectId || projectId === "shell" || !agentKey) return;
    fetch(`${API_BASE}/v1/projects`, {
      headers: { Authorization: `Bearer ${agentKey}` },
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then((j) => {
        const p = (j.projects as ProjectDetail[]).find(
          (x) => x.project_id === projectId
        );
        if (p) setProject(p);
        else setError("project not found for this key");
      })
      .catch((e) => setError(String(e)));
  }, [projectId, agentKey]);

  if (!agentKey) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <p className="text-sm text-[#8a8e93]">
          Sign in on the <a href="/app">dashboard</a> first.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <a href="/app" className="text-sm text-[#8a8e93]">
        ← dashboard
      </a>
      <h1 className="mt-4 text-2xl font-semibold tracking-tight">
        {project?.topic ?? projectId}
      </h1>
      {project && (
        <div className="mt-1 text-sm text-[#8a8e93]">
          depth: {project.depth} · status: {project.status}
        </div>
      )}
      <h2 className="mt-8 text-lg font-semibold">Findings</h2>
      {findings.length === 0 ? (
        <p className="mt-2 text-sm text-[#8a8e93]">
          Findings detail listing — wire to <code>/v1/findings</code> when
          available. (Today the public surface returns findings indirectly via{" "}
          <code>publish_report</code> and the timeline.)
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {findings.map((f) => (
            <li key={f.finding_id} className="rounded-md border border-[#1f2227] p-3">
              <div className="font-medium">{f.claim}</div>
              <div className="mt-1 text-sm text-[#a9adb1]">{f.evidence}</div>
            </li>
          ))}
        </ul>
      )}
      {error && <div className="mt-4 text-sm text-[#ffaa66]">{error}</div>}
    </main>
  );
}
