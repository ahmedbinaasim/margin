"use client";

import { useEffect, useRef, useState } from "react";
import { API_BASE, EventEnvelope, api } from "@/lib/api";

const POLL_MS = 5000;
const RETRY_SSE_MS = 30000;

export function ActivityTimeline({ token }: { token: string }) {
  const [events, setEvents] = useState<EventEnvelope[]>([]);
  const [streamErr, setStreamErr] = useState<string | null>(null);
  // Track the most-recent event_id so polling fetches only new rows.
  const lastIdRef = useRef<number>(0);

  // Initial hydration.
  useEffect(() => {
    let active = true;
    api
      .recentEvents(token)
      .then((rows) => {
        if (!active) return;
        setEvents(rows);
        if (rows.length > 0) {
          lastIdRef.current = Math.max(...rows.map((r) => r.event_id));
        }
      })
      .catch(() => {
        /* no-op; SSE may still work */
      });
    return () => {
      active = false;
    };
  }, [token]);

  // Live updates: SSE first, polling fallback on error, periodic SSE retry.
  useEffect(() => {
    let cancelled = false;
    let es: EventSource | null = null;
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const merge = (obj: EventEnvelope) => {
      setEvents((prev) => {
        if (prev.some((p) => p.event_id === obj.event_id)) return prev;
        return [obj, ...prev].slice(0, 100);
      });
      if (obj.event_id > lastIdRef.current) lastIdRef.current = obj.event_id;
    };

    const stopPolling = () => {
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    };

    const startPolling = () => {
      if (pollTimer) return;
      pollTimer = setInterval(async () => {
        try {
          const rows = await api.recentEvents(token);
          // recentEvents returns newest-first across the whole window; merge any
          // we don't already have.
          for (const r of rows) {
            if (r.event_id > lastIdRef.current) merge(r);
          }
        } catch {
          /* keep polling; transient failures are normal */
        }
      }, POLL_MS);
    };

    const openSSE = () => {
      if (cancelled) return;
      const url = `${API_BASE}/v1/events?token=${encodeURIComponent(token)}`;
      es = new EventSource(url);
      es.onopen = () => {
        if (cancelled) return;
        setStreamErr(null);
        stopPolling();
      };
      es.onmessage = (e) => {
        try {
          merge(JSON.parse(e.data) as EventEnvelope);
        } catch {
          /* ignore malformed event */
        }
      };
      es.onerror = () => {
        if (cancelled) return;
        setStreamErr("live stream disconnected — polling for updates");
        es?.close();
        es = null;
        startPolling();
        // Try to reattach the live stream after a cooling-off window.
        if (retryTimer) clearTimeout(retryTimer);
        retryTimer = setTimeout(openSSE, RETRY_SSE_MS);
      };
    };

    openSSE();

    return () => {
      cancelled = true;
      es?.close();
      stopPolling();
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [token]);

  if (events.length === 0) {
    return (
      <div className="rounded-md border border-[#1f2227] bg-[#0e1115] p-6 text-sm text-[#8a8e93]">
        No events yet. Connect Claude with your MCP URL and call{" "}
        <code className="font-mono text-[#f5dd5b]">start_research</code> — the
        timeline will populate live.
        {streamErr && (
          <div className="mt-2 text-xs text-[#ffaa66]">{streamErr}</div>
        )}
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border border-[#1f2227]">
      <table className="w-full text-left text-sm">
        <thead className="bg-[#131619] text-[#a9adb1]">
          <tr>
            <th className="px-4 py-2">Kind</th>
            <th className="px-4 py-2">Project</th>
            <th className="px-4 py-2">Detail</th>
            <th className="px-4 py-2 text-right">When</th>
          </tr>
        </thead>
        <tbody data-testid="activity-rows">
          {events.map((e, i) => (
            <tr
              key={e.event_id}
              className={i % 2 ? "bg-[#0e1115]" : "bg-[#0b0d10]"}
            >
              <td className="px-4 py-2 font-mono text-[#f5dd5b]">{e.kind}</td>
              <td className="px-4 py-2 font-mono text-xs text-[#a9adb1]">
                {e.project_id ?? "—"}
              </td>
              <td className="px-4 py-2 text-xs text-[#a9adb1]">
                {summarize(e.payload)}
              </td>
              <td className="px-4 py-2 text-right text-xs text-[#8a8e93]">
                {e.created_at?.replace("T", " ").slice(0, 19) ?? "live"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function summarize(p: Record<string, unknown>): string {
  const claim = p.claim;
  if (typeof claim === "string") return claim;
  return Object.entries(p)
    .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join(" ")
    .slice(0, 240);
}
