"use client";

import { useEffect, useState } from "react";
import {
  AgentSummary,
  CreateAgentOutput,
  ProjectSummary,
  api,
} from "@/lib/api";
import { ActivityTimeline } from "@/components/ActivityTimeline";
import { CodeBlock } from "@/components/CodeBlock";

type Stage = "signin" | "ready";

export default function Dashboard() {
  const [stage, setStage] = useState<Stage>("signin");
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [signingIn, setSigningIn] = useState(false);

  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [newAgentName, setNewAgentName] = useState("");
  const [justMinted, setJustMinted] = useState<CreateAgentOutput | null>(null);
  // Per-row UI state: id of the agent currently being renamed (if any) and the
  // draft text for that rename.
  const [editingAgentId, setEditingAgentId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");

  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [activeAgentKey, setActiveAgentKey] = useState<string | null>(null);

  // Hydrate token from localStorage on first render
  useEffect(() => {
    const t = typeof window !== "undefined" ? localStorage.getItem("margin.token") : null;
    if (t) {
      setToken(t);
      setStage("ready");
    }
    const k = typeof window !== "undefined" ? localStorage.getItem("margin.agent_key") : null;
    if (k) setActiveAgentKey(k);
  }, []);

  // Load agents and projects when ready
  useEffect(() => {
    if (stage !== "ready" || !token) return;
    api
      .listAgents(token)
      .then(setAgents)
      .catch((e) => setError(`agents: ${e.message}`));
  }, [stage, token]);

  useEffect(() => {
    if (!activeAgentKey) return;
    api
      .listProjects(activeAgentKey)
      .then((r) => setProjects(r.projects))
      .catch(() => {
        /* fresh agent has no projects yet */
        setProjects([]);
      });
  }, [activeAgentKey]);

  async function onContinueWithGoogle() {
    setError(null);
    setSigningIn(true);
    try {
      // Lazy-import the Firebase SDK so its ~80 KB chunk only loads on click.
      const { signInWithPopup, GoogleAuthProvider } = await import("firebase/auth");
      const { firebaseAuth } = await import("@/lib/firebase");
      const result = await signInWithPopup(firebaseAuth, new GoogleAuthProvider());
      const idToken = await result.user.getIdToken();
      const r = await api.authFirebase(idToken);
      localStorage.setItem("margin.token", r.token);
      setToken(r.token);
      // If we landed on /app because /app/authorize bounced us here for sign-in,
      // honor the saved redirect target now that we have a token.
      const redirect =
        typeof window !== "undefined"
          ? sessionStorage.getItem("margin.post_signin_redirect")
          : null;
      if (redirect) {
        sessionStorage.removeItem("margin.post_signin_redirect");
        window.location.href = redirect;
        return;
      }
      setStage("ready");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSigningIn(false);
    }
  }

  async function onRenameAgent(agentId: string) {
    if (!token) return;
    const trimmed = editingName.trim();
    if (!trimmed) {
      setEditingAgentId(null);
      return;
    }
    // Optimistic update
    const prev = agents;
    setAgents((rows) =>
      rows.map((r) => (r.agent_id === agentId ? { ...r, name: trimmed } : r))
    );
    setEditingAgentId(null);
    try {
      await api.updateAgent(agentId, trimmed, token);
    } catch (err) {
      setAgents(prev);
      setError(`rename failed: ${(err as Error).message}`);
    }
  }

  async function onDeleteAgent(agentId: string, prefix: string) {
    if (!token) return;
    const ok = window.confirm(
      `Revoke key ${prefix}…? The connector using this key will stop working immediately. This cannot be undone.`
    );
    if (!ok) return;
    const prev = agents;
    setAgents((rows) => rows.filter((r) => r.agent_id !== agentId));
    try {
      await api.deleteAgent(agentId, token);
    } catch (err) {
      setAgents(prev);
      setError(`delete failed: ${(err as Error).message}`);
    }
  }

  async function onMintAgent(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    try {
      const r = await api.createAgent(newAgentName || "My Agent", token);
      setJustMinted(r);
      setNewAgentName("");
      setAgents((prev) => [
        {
          agent_id: r.agent_id,
          name: r.name,
          key_prefix: r.key_prefix,
          last_used_at: null,
          created_at: new Date().toISOString(),
        },
        ...prev,
      ]);
      // Stash for project listing convenience.
      localStorage.setItem("margin.agent_key", r.api_key);
      setActiveAgentKey(r.api_key);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  function logout() {
    localStorage.removeItem("margin.token");
    localStorage.removeItem("margin.agent_key");
    setToken(null);
    setActiveAgentKey(null);
    setAgents([]);
    setProjects([]);
    setStage("signin");
  }

  if (stage === "signin") {
    return (
      <main className="mx-auto max-w-md px-6 py-24">
        <h1 className="text-2xl font-semibold tracking-tight">
          Sign in to Margin
        </h1>
        <p className="mt-2 text-sm text-[#8a8e93]">
          Continue with your Google account.
        </p>
        <button
          onClick={onContinueWithGoogle}
          disabled={signingIn}
          className="mt-6 flex w-full items-center justify-center gap-3 rounded-md bg-[#f5dd5b] px-3 py-2.5 text-sm font-medium text-black transition disabled:cursor-not-allowed disabled:opacity-60"
        >
          {signingIn ? (
            <>
              <svg
                className="h-4 w-4 animate-spin"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
                />
              </svg>
              Signing in…
            </>
          ) : (
            <>
              <svg
                className="h-4 w-4"
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 18 18"
                aria-hidden="true"
              >
                <path
                  fill="#4285F4"
                  d="M17.64 9.205c0-.639-.057-1.252-.164-1.841H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"
                />
                <path
                  fill="#34A853"
                  d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"
                />
                <path
                  fill="#FBBC05"
                  d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"
                />
                <path
                  fill="#EA4335"
                  d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"
                />
              </svg>
              Continue with Google
            </>
          )}
        </button>
        {error && <div className="mt-3 text-sm text-[#ffaa66]">{error}</div>}
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <button
          onClick={logout}
          className="rounded-md border border-[#1f2227] px-3 py-1 text-xs text-[#8a8e93] hover:text-[#e8e6e3]"
        >
          Log out
        </button>
      </header>

      <section className="mt-8">
        <h2 className="text-lg font-semibold">Agent keys</h2>
        <p className="mt-1 text-sm text-[#8a8e93]">
          Mint a key for each connector you wire up (Claude Desktop, Cursor,
          your own SDK).
        </p>
        <form onSubmit={onMintAgent} className="mt-4 flex gap-2">
          <input
            placeholder="My Agent (e.g. Sara's Claude Desktop)"
            value={newAgentName}
            onChange={(e) => setNewAgentName(e.target.value)}
            className="flex-1 rounded-md border border-[#1f2227] bg-[#0e1115] px-3 py-2 text-sm"
          />
          <button
            type="submit"
            className="rounded-md bg-[#f5dd5b] px-4 py-2 text-sm font-medium text-black"
          >
            Mint
          </button>
        </form>
        {justMinted && (
          <div className="mt-4 rounded-md border border-[#1f2227] bg-[#0e1115] p-4">
            <div className="text-xs uppercase tracking-widest text-[#8a8e93]">
              Save this key — it&apos;s shown ONCE
            </div>
            <CodeBlock className="mt-2">{justMinted.api_key}</CodeBlock>
            <div className="mt-3 text-xs uppercase tracking-widest text-[#8a8e93]">
              Add to Claude
            </div>
            <CodeBlock className="mt-2">{justMinted.mcp_url}</CodeBlock>
          </div>
        )}
        <ul className="mt-4 divide-y divide-[#1f2227] rounded-md border border-[#1f2227]">
          {agents.length === 0 && (
            <li className="px-4 py-3 text-sm text-[#8a8e93]">
              No agents yet.
            </li>
          )}
          {agents.map((a) => {
            const isEditing = editingAgentId === a.agent_id;
            return (
              <li
                key={a.agent_id}
                className="flex items-center justify-between gap-3 px-4 py-3 text-sm"
              >
                <span className="min-w-0 flex-1">
                  {isEditing ? (
                    <span className="flex items-center gap-2">
                      <input
                        autoFocus
                        value={editingName}
                        onChange={(e) => setEditingName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") onRenameAgent(a.agent_id);
                          if (e.key === "Escape") setEditingAgentId(null);
                        }}
                        className="min-w-0 flex-1 rounded border border-[#1f2227] bg-[#0e1115] px-2 py-1 text-sm"
                      />
                      <button
                        type="button"
                        onClick={() => onRenameAgent(a.agent_id)}
                        className="rounded bg-[#f5dd5b] px-2 py-1 text-xs font-medium text-black"
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditingAgentId(null)}
                        className="rounded border border-[#1f2227] px-2 py-1 text-xs text-[#8a8e93]"
                      >
                        Cancel
                      </button>
                    </span>
                  ) : (
                    <>
                      <span className="font-medium">{a.name}</span>{" "}
                      <span className="font-mono text-xs text-[#8a8e93]">
                        {a.key_prefix}…
                      </span>
                    </>
                  )}
                </span>
                {!isEditing && (
                  <>
                    <span className="text-xs text-[#8a8e93]">
                      {a.last_used_at
                        ? `last used ${a.last_used_at.slice(0, 10)}`
                        : "never used"}
                    </span>
                    <span className="flex items-center gap-1">
                      <button
                        type="button"
                        title="Rename"
                        aria-label={`Rename ${a.name}`}
                        onClick={() => {
                          setEditingAgentId(a.agent_id);
                          setEditingName(a.name);
                        }}
                        className="rounded p-1 text-[#8a8e93] hover:bg-[#1f2227] hover:text-[#e8e6e3]"
                      >
                        <svg
                          className="h-4 w-4"
                          xmlns="http://www.w3.org/2000/svg"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                          strokeWidth={2}
                          aria-hidden="true"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M15.232 5.232l3.536 3.536M9 13l6.586-6.586a2 2 0 112.828 2.828L11.828 15.828a2 2 0 01-1.414.586H8v-2.414a2 2 0 01.586-1.414z"
                          />
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M5 21h14"
                          />
                        </svg>
                      </button>
                      <button
                        type="button"
                        title="Revoke key"
                        aria-label={`Revoke ${a.name}`}
                        onClick={() => onDeleteAgent(a.agent_id, a.key_prefix)}
                        className="rounded p-1 text-[#8a8e93] hover:bg-[#1f2227] hover:text-[#ffaa66]"
                      >
                        <svg
                          className="h-4 w-4"
                          xmlns="http://www.w3.org/2000/svg"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                          strokeWidth={2}
                          aria-hidden="true"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M6 7h12M9 7V5a2 2 0 012-2h2a2 2 0 012 2v2m-7 0v12a2 2 0 002 2h6a2 2 0 002-2V7"
                          />
                        </svg>
                      </button>
                    </span>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      </section>

      <section className="mt-12">
        <h2 className="text-lg font-semibold">Projects</h2>
        <ul className="mt-4 divide-y divide-[#1f2227] rounded-md border border-[#1f2227]">
          {projects.length === 0 && (
            <li className="px-4 py-3 text-sm text-[#8a8e93]">
              No projects yet — call <code>start_research</code> from your agent.
            </li>
          )}
          {projects.map((p) => (
            <li
              key={p.project_id}
              className="flex items-center justify-between px-4 py-3 text-sm"
            >
              <a href={`/app/p/${p.project_id}`} className="font-medium">
                {p.topic}
              </a>
              <span className="text-xs text-[#8a8e93]">
                {p.num_findings} findings · {p.status}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-12">
        <h2 className="text-lg font-semibold">Activity</h2>
        <div className="mt-4">
          {token ? <ActivityTimeline token={token} /> : null}
        </div>
      </section>

      {error && <div className="mt-6 text-sm text-[#ffaa66]">{error}</div>}
    </main>
  );
}
