"use client";

import { memo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/** Turn [3] / [1, 2] markers into #cite-n links (skip real markdown links like [text](url)). */
export function linkCitations(md: string): string {
  return md.replace(/\[(\d{1,3}(?:\s*,\s*\d{1,3})*)\](?!\()/g, (_m, nums: string) =>
    nums
      .split(",")
      .map((n) => `[${n.trim()}](#cite-${n.trim()})`)
      .join(""),
  );
}

function MarkdownImpl({ content, onCite }: { content: string; onCite: (n: number) => void }) {
  const components: Components = {
    a({ href, children, ...props }) {
      if (href?.startsWith("#cite-")) {
        const n = Number(href.slice(6));
        return (
          <button
            type="button"
            onClick={() => onCite(n)}
            className="bg-primary/10 text-primary hover:bg-primary hover:text-primary-foreground mx-px inline-flex h-4 min-w-4 -translate-y-1 items-center justify-center rounded px-1 align-baseline text-[10px] leading-none font-semibold no-underline"
            aria-label={`Source ${n}`}
          >
            {n}
          </button>
        );
      }
      return (
        <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
          {children}
        </a>
      );
    },
    table({ children }) {
      return (
        <div className="not-prose my-4 overflow-x-auto rounded-lg border">
          <table>{children}</table>
        </div>
      );
    },
  };
  return (
    <div className="answer-md prose prose-sm dark:prose-invert prose-headings:font-semibold prose-h2:text-lg prose-h3:text-base prose-h2:mt-5 prose-h3:mt-4 prose-p:my-2 prose-li:my-0.5 max-w-none">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {linkCitations(content)}
      </ReactMarkdown>
    </div>
  );
}

export const Markdown = memo(MarkdownImpl);
