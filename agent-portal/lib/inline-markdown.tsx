import * as React from "react";

/**
 * Formata o markdown inline que o LLM costuma usar nas respostas do chat
 * (`**negrito**` e `` `código` ``) como elementos React, sem HTML cru
 * (nada de dangerouslySetInnerHTML). O restante do texto fica literal.
 */
export function renderInlineMarkdown(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/g);
  return parts.map((part, i) => {
    if (part.length > 4 && part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (part.length > 2 && part.startsWith("`") && part.endsWith("`")) {
      return (
        <code
          key={i}
          style={{ fontFamily: "var(--font-mono)", fontSize: "0.92em", padding: "0 3px" }}
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
}
