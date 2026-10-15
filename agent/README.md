# SPE agent

Task 6 provides configuration; Task 7 provides the open-terminal adapter in
`src/spe_agent/sandbox.py`. The agent loop and HTTP service are not implemented yet.

Run the offline tests with `uv run --group dev pytest -q` from this directory.

## Sandbox tools

`operations_from_openapi` generates the 16 operations in the pinned fixture;
`select_operations` validates an allowlist, and `build_tools` binds each operation
using `Tool.from_schema` (verified in installed pydantic-ai 2.56.0 source).
`SandboxClient` supports discovery, optional cwd/system prompt, and authenticated
calls. Its owner must call `aclose()` at shutdown; injected HTTP clients remain
owned by their caller. Discovery failures raise `SandboxUnavailable` for later
readiness/retry handling. Optional metadata failures return `None`.

Fixture provenance, recorded by the preceding session: captured `/openapi.json`
from `ghcr.io/open-webui/open-terminal:0.12.4`, digest
`sha256:ca1d60e70f4eca35db62b80b128fffc7d7c156298167aac25cc4982947bcea5b`.
The fixture reports source version 0.12.4. It contains no runtime credentials.
The reference is Open WebUI v0.11.3 `backend/open_webui/utils/tools.py`.

Parity: local schema references are resolved without network access; path/query
parameters follow the baseline string fallback and enum descriptions. Body
properties are merged and nullable singleton schemas cleaned. Mutating requests
send all arguments when a body is defined, otherwise `{}`. Optional empty query
values are omitted; missing/null required values produce errors. The cwd suffix
is added to `run_command`, and a supplied session id becomes `X-Session-Id`.

Differences and limits:

- No Open WebUI-only `display_file` inline/page parameters or base64 binary data
  URIs. Non-JSON and malformed JSON are returned as UTF-8 text with replacement.
- Remote/unresolvable/cyclic schema references resolve to empty schemas. The
  pinned fixture requires no recursive schema support.
- Redirects are errors; the configured HTTP(S) origin alone receives the bearer
  header. Model arguments cannot set headers or origin. Path values are encoded
  as single segments; empty values and literal dot segments are rejected.
  Encoded traversal values remain escaped at the HTTP transport boundary. This
  does not promise confinement through a proxy that repeatedly decodes paths.
- Calls have a 30-second total deadline and HTTP timeout. Responses are streamed
  in 64 KiB chunks, retaining at most 1 MiB while counting the full decoded HTTP
  body for the truncation marker. Counting stops at the deadline, returning a
  timeout error for a never-ending stream. Oversized discovery is rejected.
- Tool results, including the truncation marker, fit `max_output_bytes`. The
  marker's total is the original response byte count; shown bytes count UTF-8
  output after replacement/redaction. For caps too small to fit a marker, only
  its leading bytes are returned. A truncated result is not necessarily JSON.
- Sandbox credentials are redacted from responses; transport exception details
  are not exposed. Owned clients disable environment proxy settings.

Validation: 50 sandbox tests and 7 configuration tests pass offline. No live
sandbox deployment or paid model calls are needed for Task 7.
