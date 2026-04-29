"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ReportPublic, api } from "@/lib/api";

export function generateStaticParams() {
  return [{ slug: "shell" }];
}

export const dynamicParams = true;

export default function ReportViewer() {
  const params = useParams<{ slug: string }>();
  const slug = params?.slug ?? "";
  const [report, setReport] = useState<ReportPublic | null>(null);
  const [error, setError] = useState<string | null>(null);

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
        Published via <a href="/">Margin</a> ·{" "}
        {report.created_at.slice(0, 19).replace("T", " ")}
      </footer>
    </main>
  );
}
