// Tiny typed fetch wrappers used by the dashboard.

export const API_BASE =
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE) ||
  "http://localhost:8080";

export type AuthVerifyOutput = { token: string; owner_id: string };
export type AgentSummary = {
  agent_id: string;
  name: string;
  key_prefix: string;
  last_used_at: string | null;
  created_at: string;
};
export type CreateAgentOutput = AgentSummary & {
  api_key: string;
  mcp_url: string;
};
export type ProjectSummary = {
  project_id: string;
  topic: string;
  depth: string;
  status: string;
  num_findings: number;
  parent_id: string | null;
  updated_at: string;
  created_at: string;
};
export type EventEnvelope = {
  event_id: number;
  agent_id: string;
  project_id: string | null;
  kind: string;
  payload: Record<string, unknown>;
  created_at?: string;
};
export type OAuthClientPublic = {
  client_id: string;
  client_name: string;
  redirect_uris: string[];
  grant_types: string[];
  response_types: string[];
  token_endpoint_auth_method: string;
  logo_uri?: string | null;
  client_uri?: string | null;
  software_id?: string | null;
  software_version?: string | null;
  created_at: string;
};
export type OAuthAuthorizeDecisionInput = {
  decision: "allow" | "deny";
  auth_request: string;
};
export type ReportPublic = {
  report_id: string;
  project_id: string;
  format: string;
  public_slug: string;
  body: string;
  created_at: string;
};

class HttpError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  init: RequestInit & { auth?: string } = {}
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init.headers as Record<string, string>) ?? {}),
  };
  if (init.auth) headers.Authorization = `Bearer ${init.auth}`;
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = (j.detail ?? JSON.stringify(j)) as string;
    } catch {
      /* ignore */
    }
    throw new HttpError(`${res.status} ${detail}`, res.status);
  }
  return (await res.json()) as T;
}

export const api = {
  authFirebase(idToken: string) {
    return request<AuthVerifyOutput>("/v1/auth/firebase", {
      method: "POST",
      body: JSON.stringify({ id_token: idToken }),
    });
  },
  listAgents(token: string) {
    return request<AgentSummary[]>("/v1/agents", { auth: token });
  },
  createAgent(name: string, token: string) {
    return request<CreateAgentOutput>("/v1/agents", {
      method: "POST",
      auth: token,
      body: JSON.stringify({ name }),
    });
  },
  updateAgent(agentId: string, name: string, token: string) {
    return request<AgentSummary>(`/v1/agents/${encodeURIComponent(agentId)}`, {
      method: "PATCH",
      auth: token,
      body: JSON.stringify({ name }),
    });
  },
  async deleteAgent(agentId: string, token: string): Promise<void> {
    const headers: Record<string, string> = {
      Authorization: `Bearer ${token}`,
    };
    const res = await fetch(
      `${API_BASE}/v1/agents/${encodeURIComponent(agentId)}`,
      { method: "DELETE", headers }
    );
    if (!res.ok && res.status !== 204) {
      throw new HttpError(`${res.status} ${res.statusText}`, res.status);
    }
  },
  listProjects(agentKey: string) {
    return request<{ projects: ProjectSummary[]; total: number }>(
      "/v1/projects",
      { auth: agentKey }
    );
  },
  recentEvents(token: string) {
    return request<EventEnvelope[]>(
      `/v1/events/recent?token=${encodeURIComponent(token)}`
    );
  },
  getReport(slug: string) {
    return request<ReportPublic>(`/v1/reports/${encodeURIComponent(slug)}`);
  },
  startResearch(agentKey: string, topic: string, depth = "standard") {
    return request<ProjectSummary & { dashboard_url: string }>("/v1/projects", {
      method: "POST",
      auth: agentKey,
      body: JSON.stringify({ topic, depth }),
    });
  },
  getOAuthClient(clientId: string, token: string) {
    return request<OAuthClientPublic>(
      `/v1/oauth/clients/${encodeURIComponent(clientId)}`,
      { auth: token }
    );
  },
  authorizeDecision(input: OAuthAuthorizeDecisionInput, token: string) {
    return request<{ redirect_to: string }>("/v1/oauth/authorize-decision", {
      method: "POST",
      auth: token,
      body: JSON.stringify(input),
    });
  },
};
