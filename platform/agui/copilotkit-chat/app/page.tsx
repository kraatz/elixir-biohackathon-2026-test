"use client";
// Full-screen chat with agent `spe`. Each tool call is a collapsible card: name, status,
// arguments and the first lines of the result. Everything is rendered as text, never HTML.
// No persistence: a reload starts a new conversation.
import { CopilotChat, CopilotKitProvider, useDefaultRenderTool } from "@copilotkit/react-core/v2";
import { useState } from "react";

const MAX_RESULT_LINES = 40;
const MAX_RESULT_CHARS = 4000;

type ToolProps = {
  name: string;
  parameters: unknown;
  status: "inProgress" | "executing" | "complete";
  result: string | undefined;
};

function preview(result: string): string {
  let text = result;
  try {
    text = JSON.stringify(JSON.parse(result), null, 2);
  } catch {
    // not JSON: show as is
  }
  const lines = text.split("\n");
  let shown = lines.slice(0, MAX_RESULT_LINES).join("\n");
  if (shown.length > MAX_RESULT_CHARS) shown = shown.slice(0, MAX_RESULT_CHARS);
  return shown.length < text.length ? `${shown}\n… (${text.length - shown.length} more characters)` : shown;
}

function brief(name: string, parameters: unknown): string {
  if (parameters && typeof parameters === "object") {
    const p = parameters as Record<string, unknown>;
    for (const key of ["command", "path", "pattern", "query", "process_id"]) {
      if (typeof p[key] === "string" || typeof p[key] === "number") return String(p[key]);
    }
  }
  return "";
}

const STATUS: Record<ToolProps["status"], string> = {
  inProgress: "preparing…",
  executing: "running…",
  complete: "done",
};

function ToolCard({ name, parameters, status, result }: ToolProps) {
  return (
    <details className="spe-tool">
      <summary>
        <span className="spe-tool-name">{name}</span>
        <span className="spe-tool-brief">{brief(name, parameters)}</span>
        <span className="spe-tool-status">{STATUS[status]}</span>
      </summary>
      <div className="spe-tool-label">arguments</div>
      <pre>{JSON.stringify(parameters ?? {}, null, 2)}</pre>
      {result !== undefined && (
        <>
          <div className="spe-tool-label">result</div>
          <pre>{preview(result)}</pre>
        </>
      )}
    </details>
  );
}

function Chat() {
  const [error, setError] = useState<string | null>(null);
  useDefaultRenderTool({ render: (props) => <ToolCard {...props} /> });
  return (
    <div className="spe-page">
      <div className="spe-header">SPE agent — every tool call is shown; a reload starts a new conversation.</div>
      {error && (
        <div className="spe-error" role="alert">
          {error}
          <button type="button" onClick={() => setError(null)}>dismiss</button>
        </div>
      )}
      <CopilotChat
        agentId="spe"
        className="spe-chat"
        onError={(event) => {
          // The prop's type also admits a DOM error event; only CopilotKit's carries `error`.
          if ("error" in event && event.error instanceof Error) setError(event.error.message || "The agent run failed.");
        }}
      />
    </div>
  );
}

export default function Page() {
  return (
    <CopilotKitProvider runtimeUrl="/api/copilotkit" agentId="spe" showDevConsole={false}>
      <Chat />
    </CopilotKitProvider>
  );
}
