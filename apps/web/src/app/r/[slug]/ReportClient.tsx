"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ReportPublic, api } from "@/lib/api";

export function ReportClient({ slug: initialSlug }: { slug: string }) {
  const [slug, setSlug] = useState(initialSlug);
  const [report, setReport] = useState<ReportPublic | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Static export pre-renders the route as /r/shell; the actual slug lives
  // at runtime in the URL path. Override on mount.
  useEffect(() => {
    if (typeof window !== "undefined") {
      const m = window.location.pathname.match(/^\/r\/([^/]+)/);
      if (m && m[1] && m[1] !== "shell") setSlug(decodeURIComponent(m[1]));
    }
  }, []);

  useEffect(() => {
    if (!slug || slug === "shell") return;
    api
      .getReport(slug)
      .then(setReport)
      .catch((e: Error) => setError(e.message));
  }, [slug]);

  if (error) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-16 text-sm text-[#ffaa66]">
        {error}
      </main>
    );
  }
  if (!report) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-16 text-sm text-[#8a8e93]">
        Loading report {slug}…
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <article className="prose prose-invert max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{report.body}</ReactMarkdown>
      </article>
      <footer className="mt-12 border-t border-[#1f2227] pt-6 text-xs text-[#8a8e93]">
        Published via <Link href="/">Margin</Link> ·{" "}
        {report.created_at.slice(0, 19).replace("T", " ")}
      </footer>
    </main>
  );
}
