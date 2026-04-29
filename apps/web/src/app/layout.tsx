import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Margin — the research workspace for AI agents",
  description:
    "Margin gives your agents persistent, typed, citation-backed state across sessions and models. Eight primitives. MCP + REST. Free for solo developers.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
