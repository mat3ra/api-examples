# AGENTS.md — Mat3ra MCP Server

Reference document for AI agents, coding assistants, and future contributors
working on this codebase. Describes the architecture, extension points, and
conventions to follow.

---

## Repository Layout

```
mcp_server/
├── server.py        # MCP stdio server  (tools exposed to LLM clients)
├── code_server.py   # HTTP playground   (prompt → Python code, browser UI)
├── intent.py        # Intent detection  (rules + 6 LLM backends)
├── pyproject.toml   # Package manifest + optional deps
├── .env.example     # Credential template
├── README.md        # User-facing documentation
└── AGENTS.md        # This file
```

---

## Key Abstractions

### 1. Tool Catalogue (`intent.py → TOOLS`)

`TOOLS` is the single source of truth for all Mat3ra API operations.
Each entry drives **three** things simultaneously:

- The **LLM system prompt** (tool names, args, descriptions)
- The **JSON schema** exposed by the MCP server (`server.py → list_tools`)
- The **Python code generation** (`intent.py → _build_call`)

When adding a new Mat3ra API operation, add it to `TOOLS` first — everything else derives from it.

```python
TOOLS: dict[str, dict] = {
    "my_new_tool": {
        "module": "materials",          # mat3ra.api_client.endpoints.<module>
        "cls":    "MaterialEndpoints",  # endpoint class
        "description": "...",           # shown to the LLM
        "args_schema": {                # used in system prompt + MCP schema
            "param_name": "description of param",
        },
    },
}
```

Then add a matching `elif tool == "my_new_tool":` branch in `_build_call()` and
a matching `Tool(...)` entry in `server.py → list_tools()` and handler branch in
`server.py → _dispatch()`.

### 2. Intent Detection (`intent.py → detect_intent`)

```python
def detect_intent(prompt: str, backend: str | None = None) -> dict:
    ...
```

Returns:

```python
{
    "tool":    str,   # e.g. "list_materials"
    "args":    dict,  # e.g. {"formula": "Si"}
    "module":  str,   # e.g. "materials"
    "cls":     str,   # e.g. "MaterialEndpoints"
    "call":    str,   # Python call snippet
    "code":    str,   # Full runnable Python script
    "backend": str,   # Which backend was actually used
}
```

All LLM backends receive the same `SYSTEM_PROMPT` (auto-generated from `TOOLS`)
and return raw text that is parsed by `_parse_llm_json()`. Any backend that
raises an exception automatically falls back to `rules`.

### 3. LLM Backends (`intent.py → _BACKENDS`)

| Key | Function | Transport |
|---|---|---|
| `rules` | `_rules()` | regex, no network |
| `openai` | `_openai()` | HTTPS to api.openai.com |
| `claude` | `_claude()` | HTTPS to api.anthropic.com |
| `gemini` | `_gemini()` | HTTPS to generativelanguage.googleapis.com |
| `local` | `_local()` | HTTP to localhost:11434 (Ollama) |
| `hf` | `_huggingface()` | in-process, HuggingFace transformers |

Each backend function signature: `(prompt: str) -> tuple[str, dict]`
i.e. `(tool_name, args_dict)`.

To add a new backend:
1. Write `def _mybackend(prompt: str) -> tuple[str, dict]` in `intent.py`
2. Add `"mybackend": _mybackend` to `_BACKENDS`
3. Add `<option value="mybackend">...</option>` to the `<select>` in `code_server.py`
4. Add an optional dep to `pyproject.toml` if needed

### 4. MCP Server (`server.py`)

Uses the [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
low-level `Server` API (not `FastMCP`) for explicit control.

- `@server.list_tools()` — advertises the tool catalogue to MCP clients
- `@server.call_tool()` — dispatches to `_dispatch(name, arguments)`
- `_dispatch()` — creates the appropriate `*Endpoints` object and calls it
- Credentials are read from env vars at **call time** (not import time), so the
  server can start before credentials are set.

Transport: **stdio** (newline-framed JSON-RPC with Content-Length headers,
handled by the MCP SDK). The server is meant to be launched by an MCP client
(Claude Desktop, Cursor, etc.) as a child process.

### 5. HTTP Playground (`code_server.py`)

Pure stdlib (`http.server`) — no framework dependencies.

- `GET /` → serves the HTML+JS playground
- `POST /ask` → `{ prompt, backend }` → calls `detect_intent()` → returns intent dict
- The `backend` field in the POST body overrides the `INTENT_BACKEND` env var

---

## Conventions

### Credentials
- Never hard-code credentials. Always read from environment variables.
- Prefix: `MAT3RA_*` for platform creds, backend-specific prefixes for LLM keys.
- The server starts successfully even with missing creds; errors surface at call time.

### Error handling
- LLM backends catch all exceptions and fall back to `rules` automatically.
- API errors from Mat3ra are returned as `TextContent` with `"Error: ..."` text
  (not as MCP error responses) so the client can display them gracefully.
- HTTP server returns `{"error": "..."}` JSON with HTTP 200 for application-level
  errors so the browser UI can display them inline.

### Code generation
- Generated code is always a **complete, runnable script** — includes imports,
  credential loading, endpoint construction, and the API call.
- Placeholder values like `<material_id>` use angle-bracket convention so they
  are obviously not real values.

### HuggingFace pipeline caching
- `_hf_pipeline_cache` is a module-level dict keyed by `(model_id, device)`.
- The model is loaded **once** per server process on the first request and reused.
- This means the first HF request is slow (model load + optional download);
  all subsequent requests are fast.

---

## Adding a New Mat3ra API Endpoint

Checklist:

- [ ] Add entry to `TOOLS` dict in `intent.py`
- [ ] Add code generation branch in `_build_call()` in `intent.py`
- [ ] Add `Tool(...)` definition in `list_tools()` in `server.py`
- [ ] Add dispatch branch in `_dispatch()` in `server.py`
- [ ] Add keyword patterns in `_rules()` in `intent.py` (for rule-based fallback)
- [ ] Test with `curl -X POST http://localhost:8888/ask -d '{"prompt":"..."}'`

---

## Running Locally

```bash
# 1. Create venv (Python 3.10+)
python3.11 -m venv mcp_server/.venv
source mcp_server/.venv/bin/activate

# 2. Install core deps
pip install mcp mat3ra-api-client

# 3. Optional: install one or more LLM backends
pip install openai                    # OpenAI
pip install anthropic                 # Claude
pip install google-genai              # Gemini
pip install transformers accelerate torch  # HuggingFace

# 4. Set credentials
export MAT3RA_ACCOUNT_ID=...
export MAT3RA_AUTH_TOKEN=...

# 5a. Run the MCP server (for Claude Desktop / Cursor)
python mcp_server/server.py

# 5b. Run the HTTP playground
python mcp_server/code_server.py
# → http://localhost:8888
```

---

## Testing a Backend Without Real Credentials

The HTTP playground runs and generates code with **any** backend, even without
Mat3ra credentials (code generation does not call the API).

The MCP server will start and respond to `tools/list` without credentials;
actual `tools/call` requests will return a `401` error from the Mat3ra API,
which is the expected failure mode for missing credentials.

```bash
# Test code generation (no creds needed)
curl -s -X POST http://localhost:8888/ask \
     -H "Content-Type: application/json" \
     -d '{"prompt": "Find all GaAs materials", "backend": "rules"}' \
     | python3 -m json.tool
```
