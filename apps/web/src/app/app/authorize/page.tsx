"use client";

// OAuth consent screen. The backend's /oauth/authorize endpoint validates the
// incoming auth request and 302s the browser here with a signed `auth_request`
// blob in the query string. We display a confirmation card; on Approve, the
// dashboard POSTs the blob back to /v1/oauth/authorize-decision with the
// owner's Firebase JWT, gets back a redirect URL, and navigates the browser
// to the client's redirect_uri (which is on Claude.ai's domain).

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { OAuthClientPublic, api } from "@/lib/api";

export default function AuthorizePage() {
  return (
    <Suspense fallback={<Loading label="Loading…" />}>
      <AuthorizeInner />
    </Suspense>
  );
}

function AuthorizeInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const authRequest = searchParams.get("auth_request");

  const [token, setToken] = useState<string | null>(null);
  const [client, setClient] = useState<OAuthClientPublic | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!authRequest) {
      setError("missing auth_request — open this page from Claude or another MCP client");
      return;
    }
    const t = typeof window !== "undefined" ? localStorage.getItem("margin.token") : null;
    if (!t) {
      // Stash where we want to come back to AFTER sign-in completes.
      try {
        sessionStorage.setItem(
          "margin.post_signin_redirect",
          window.location.pathname + window.location.search
        );
      } catch {
        /* ignore quota issues */
      }
      router.push("/app");
      return;
    }
    setToken(t);

    let clientId: string | null = null;
    try {
      // The blob is a JWT — body is the middle segment, base64url-decoded.
      const parts = authRequest.split(".");
      if (parts.length >= 2) {
        const payload = JSON.parse(
          atob(parts[1].replace(/-/g, "+").replace(/_/g, "/").padEnd(parts[1].length + (4 - (parts[1].length % 4)) % 4, "="))
        );
        clientId = payload.client_id ?? null;
      }
    } catch {
      // ignore — backend re-validates anyway
    }
    if (!clientId) {
      setError("auth_request looks malformed");
      return;
    }
    api
      .getOAuthClient(clientId, t)
      .then(setClient)
      .catch((e) => setError(`couldn't load client metadata: ${(e as Error).message}`));
  }, [authRequest, router]);

  async function decide(decision: "allow" | "deny") {
    if (!authRequest || !token) return;
    setSubmitting(true);
    setError(null);
    try {
      const r = await api.authorizeDecision({ decision, auth_request: authRequest }, token);
      window.location.href = r.redirect_to;
    } catch (e) {
      setError((e as Error).message);
      setSubmitting(false);
    }
  }

  if (error) {
    return (
      <Shell>
        <div className="text-sm text-[#ffaa66]">{error}</div>
      </Shell>
    );
  }
  if (!token || !client) {
    return <Loading label="Verifying request…" />;
  }

  const redirectHost = (() => {
    try {
      return client.redirect_uris[0] ? new URL(client.redirect_uris[0]).host : "—";
    } catch {
      return client.redirect_uris[0] ?? "—";
    }
  })();

  return (
    <Shell>
      <h1 className="text-xl font-semibold tracking-tight">
        <span className="text-[#f5dd5b]">{client.client_name}</span> wants to connect to Margin
      </h1>
      <p className="mt-3 text-sm text-[#a9adb1]">
        Approving creates a new agent under your account and authorizes the client to act
        as that agent. You can rename or revoke it any time from your dashboard.
      </p>

      <ul className="mt-6 space-y-2 text-sm text-[#a9adb1]">
        <li className="flex gap-2">
          <span className="text-[#f5dd5b]">•</span> Start research projects in your workspace
        </li>
        <li className="flex gap-2">
          <span className="text-[#f5dd5b]">•</span> Add findings and citations
        </li>
        <li className="flex gap-2">
          <span className="text-[#f5dd5b]">•</span> Search your research with semantic queries
        </li>
        <li className="flex gap-2">
          <span className="text-[#f5dd5b]">•</span> Publish reports
        </li>
      </ul>

      <div className="mt-6 rounded-md border border-[#1f2227] bg-[#0e1115] p-3 text-xs text-[#8a8e93]">
        Will redirect to: <span className="font-mono text-[#a9adb1]">{redirectHost}</span>
      </div>

      <div className="mt-6 flex gap-3">
        <button
          onClick={() => decide("allow")}
          disabled={submitting}
          className="flex-1 rounded-md bg-[#f5dd5b] px-3 py-2.5 text-sm font-medium text-black transition disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Working…" : "Approve"}
        </button>
        <button
          onClick={() => decide("deny")}
          disabled={submitting}
          className="flex-1 rounded-md border border-[#1f2227] bg-[#0e1115] px-3 py-2.5 text-sm font-medium text-[#a9adb1] transition hover:text-[#e8e6e3] disabled:cursor-not-allowed disabled:opacity-60"
        >
          Deny
        </button>
      </div>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-md px-6 py-24">
      <div className="mb-8 font-mono text-lg font-semibold tracking-tight text-[#f5dd5b]">
        Margin
      </div>
      <div className="rounded-md border border-[#1f2227] bg-[#0b0d10] p-6">{children}</div>
    </main>
  );
}

function Loading({ label }: { label: string }) {
  return (
    <Shell>
      <div className="flex items-center gap-3 text-sm text-[#8a8e93]">
        <svg className="h-4 w-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
        </svg>
        {label}
      </div>
    </Shell>
  );
}
