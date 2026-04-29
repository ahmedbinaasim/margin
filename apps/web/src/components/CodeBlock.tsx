"use client";
import { useState } from "react";

export function CodeBlock({
  children,
  className = "",
}: {
  children: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  const onCopy = () => {
    navigator.clipboard.writeText(children);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className={`relative ${className}`}>
      <pre
        className="overflow-x-auto rounded-md border border-[#1f2227] bg-[#131619] px-4 py-3 text-sm leading-relaxed text-[#e8e6e3]"
        data-testid="code-block"
      >
        <code>{children}</code>
      </pre>
      <button
        onClick={onCopy}
        className="absolute right-2 top-2 rounded border border-[#1f2227] bg-[#0b0d10] px-2 py-1 text-xs text-[#8a8e93] hover:text-[#e8e6e3]"
        aria-label="Copy"
        type="button"
      >
        {copied ? "copied" : "copy"}
      </button>
    </div>
  );
}
