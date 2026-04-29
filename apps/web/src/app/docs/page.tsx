import { CodeBlock } from "@/components/CodeBlock";
import { PrimitivesTable } from "@/components/PrimitivesTable";

export default function DocsPage() {
  return (
    <main className="mx-auto max-w-5xl px-6 py-16">
      <a href="/" className="text-sm text-[#8a8e93]">
        ← back to home
      </a>
      <h1 className="mt-4 text-3xl font-semibold tracking-tight">Docs</h1>
      <p className="mt-2 text-[#a9adb1]">
        Two transports — MCP (for Claude/Cursor connectors) and REST (for
        scripts and CI). Same eight primitives.
      </p>

      <h2 className="mt-10 text-xl font-semibold">Auth</h2>
      <p className="mt-2 text-[#a9adb1]">
        Mint an API key on the{" "}
        <a href="/app">dashboard</a>. The key works as both a Bearer token and
        a path segment (Claude.ai connectors don&apos;t support custom headers,
        so we put it in the URL).
      </p>
      <CodeBlock className="mt-3">
        {`# REST
curl -H "Authorization: Bearer ag_live_..." https://api.margin.dev/v1/projects

# MCP (Claude Desktop / Cursor connector URL)
https://api.margin.dev/mcp/ag_live_...`}
      </CodeBlock>

      <PrimitivesTable />

      <h2 className="mt-10 text-xl font-semibold">OpenAPI</h2>
      <p className="mt-2 text-[#a9adb1]">
        FastAPI auto-generates the spec at{" "}
        <a href="https://api.margin.dev/openapi.json">/openapi.json</a>. The
        same schema drives the Python SDK in{" "}
        <a href="https://github.com/ahmedbinaasim/margin/tree/main/packages/sdk-py">
          packages/sdk-py
        </a>
        .
      </p>
    </main>
  );
}
