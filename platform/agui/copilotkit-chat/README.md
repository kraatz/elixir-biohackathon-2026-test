# SPE chat UI

Next.js 16.4.1 + CopilotKit 1.79.0 (v2 API), a thin client for the SPE agent.

- `app/api/copilotkit/[[...slug]]/route.ts`: `CopilotRuntime` (`@copilotkit/runtime/v2`) in
  multi-route mode (`/api/copilotkit/info`, `/api/copilotkit/agent/spe/run`, …) via
  `createCopilotRuntimeHandler({ basePath: "/api/copilotkit" })`, with one agent `spe`: an
  `HttpAgent` (`@ag-ui/client` 1.0.2) for `AGENT_URL` sending `Authorization: Bearer
  $AGENT_API_KEY`. Both variables are server-side only (not `NEXT_PUBLIC_*`) and read on the
  first request, so the build needs neither.
- `app/page.tsx`: full-screen `CopilotChat` (`@copilotkit/react-core/v2`); every tool call is a
  collapsible card (`useDefaultRenderTool`) with name, status, arguments and the first 40 lines
  or 4000 characters of the result, rendered as text. Run errors appear in a bar above the chat.
  No persistence: a reload starts a new conversation.

Telemetry is off in the image: `NEXT_TELEMETRY_DISABLED=1`, `COPILOTKIT_TELEMETRY_DISABLED=true`,
`DO_NOT_TRACK=1` (the runtime's `/info` then tells the browser client the same).

```bash
npm ci && npm run build                       # type-checks too
# against the scripted agent (no LLM): in ../pydantic-ai-agent
#   uv run --group dev python ../../dev/fake_agent.py --port 18100 --key TEST_KEY
AGENT_URL=http://127.0.0.1:18100/agent AGENT_API_KEY=TEST_KEY PORT=3000 node .next/standalone/server.js
#   (copy .next/static to .next/standalone/.next/static first; the Dockerfile does)
docker build -t spe-chat-ui .                 # node:24-slim, user node, port 3000
```

The image runs with a read-only root filesystem when `/tmp` and `/app/.next/cache` are tmpfs
(uid 1000), with `cap_drop: ALL` and `no-new-privileges`.

TypeScript is pinned to 6.0.3: TypeScript 7 has no JavaScript API, which `next build` uses for its
type check.
