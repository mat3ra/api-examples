# Mat3ra MCP Server

Proof-of-concept [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server
and HTTP prompt-to-code playground for the [Mat3ra](https://platform.mat3ra.com/) REST API.

## Files

| File | Purpose |
|---|---|
| `server.py` | MCP server (stdio transport) — for Claude Desktop, Cursor, etc. |
| `code_server.py` | HTTP playground at `localhost:8888` — prompt → Python code |
| `intent.py` | Intent detection module (rules + LLM backends) |
| `pyproject.toml` | Package manifest and optional deps |
| `.env.example` | Credential template |
| `AGENTS.md` | Architecture notes for AI agents / future contributors |

---

## MCP Server (`server.py`)

Exposes 7 Mat3ra API operations as MCP tools:

| Tool | Description |
|---|---|
| `list_materials` | Search materials by formula or Mongo query |
| `get_material` | Fetch one material by ID |
| `create_material` | Upload a new material from a JSON config |
| `list_workflows` | List workflows |
| `list_jobs` | List jobs |
| `create_and_submit_job` | Create + submit a job (needs material + workflow IDs) |
| `get_job` | Fetch a job and its current status |

### Setup

```bash
# Python 3.10+ required
python3.11 -m venv .venv
source .venv/bin/activate
pip install mcp mat3ra-api-client
```

### Credentials

```bash
cp mcp_server/.env.example mcp_server/.env
# edit .env — get tokens from:
# https://platform.mat3ra.com → Account Preferences → API Tokens
export MAT3RA_ACCOUNT_ID=your_account_id
export MAT3RA_AUTH_TOKEN=your_auth_token
```

### Run

```bash
python mcp_server/server.py
```

### Claude Desktop integration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mat3ra": {
      "command": "/path/to/.venv/bin/python",
      "args": ["/path/to/api-examples/mcp_server/server.py"],
      "env": {
        "MAT3RA_ACCOUNT_ID": "your_account_id",
        "MAT3RA_AUTH_TOKEN":  "your_auth_token"
      }
    }
  }
}
```

Restart Claude Desktop. You can then ask:
- *"List my Si materials on Mat3ra"*
- *"Create an FCC copper material"*
- *"What is the status of job `abc123`?"*

---

## HTTP Playground (`code_server.py`)

Accepts a natural-language prompt and returns the equivalent Python API code.
Includes a browser UI with an LLM backend selector.

### Run

```bash
python mcp_server/code_server.py
# open http://localhost:8888
```

### API

```bash
curl -X POST http://localhost:8888/ask \
     -H "Content-Type: application/json" \
     -d '{"prompt": "List my silicon materials", "backend": "rules"}'
```

Response:

```json
{
  "tool":    "list_materials",
  "args":    {"formula": "Si"},
  "backend": "rules",
  "code":    "import os\nfrom mat3ra.api_client ..."
}
```

---

## Intent Detection Backends (`intent.py`)

The `backend` field (request body or `INTENT_BACKEND` env var) selects how prompts are interpreted:

| Backend | How it works | Requires |
|---|---|---|
| `rules` | Keyword regex — zero deps, always works | nothing |
| `openai` | GPT-4o-mini via OpenAI API | `pip install openai` + `OPENAI_API_KEY` |
| `claude` | Claude 3.5 Haiku via Anthropic API | `pip install anthropic` + `ANTHROPIC_API_KEY` |
| `gemini` | Gemini 2.0 Flash via Google API | `pip install google-genai` + `GEMINI_API_KEY` |
| `local` | Any Ollama model (default: `llama3.2`) | Ollama running + `OLLAMA_MODEL` |
| `hf` | HuggingFace Transformers on-device | `pip install transformers accelerate torch` |

All LLM backends share the same structured system prompt and fall back to `rules` on error.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `MAT3RA_ACCOUNT_ID` | — | Mat3ra account ID (**required**) |
| `MAT3RA_AUTH_TOKEN` | — | Mat3ra auth token (**required**) |
| `MAT3RA_ORGANIZATION_ID` | — | Org ID (optional, overrides personal account) |
| `MAT3RA_API_HOST` | `platform.mat3ra.com` | API hostname |
| `MAT3RA_API_PORT` | `443` | API port |
| `MAT3RA_API_VERSION` | `2018-10-01` | API version |
| `MAT3RA_API_SECURE` | `true` | Use HTTPS |
| `INTENT_BACKEND` | `rules` | Default intent backend |
| `OPENAI_API_KEY` | — | Required for `openai` backend |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model |
| `ANTHROPIC_API_KEY` | — | Required for `claude` backend |
| `ANTHROPIC_MODEL` | `claude-3-5-haiku-latest` | Anthropic model |
| `GEMINI_API_KEY` | — | Required for `gemini` backend |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.2` | Ollama model name |
| `HF_MODEL` | `Qwen/Qwen2.5-1.5B-Instruct` | HuggingFace model repo ID |
| `HF_DEVICE` | `auto` | `cpu`, `cuda`, `mps`, or `auto` |

### Install LLM backends

```bash
# OpenAI
pip install openai

# Claude
pip install anthropic

# Gemini
pip install google-genai

# HuggingFace (on-device)
pip install transformers accelerate
pip install torch                           # Apple Silicon / CPU
# or for CUDA:
pip install torch --index-url https://download.pytorch.org/whl/cu121

# All at once
pip install ".[all-llm]"
```

### Recommended HuggingFace models

| Model | Size | Notes |
|---|---|---|
| `Qwen/Qwen2.5-0.5B-Instruct` | ~1 GB | Fastest, runs on any CPU |
| `Qwen/Qwen2.5-1.5B-Instruct` | ~3 GB | **Default** — good balance |
| `HuggingFaceTB/SmolLM2-1.7B-Instruct` | ~3 GB | Very capable for its size |
| `microsoft/Phi-3-mini-4k-instruct` | ~8 GB | High quality |

---

## How It Works — Prompt to API

```
User: "List my silicon materials"
         │
         ▼
   intent.py  detect_intent(prompt, backend)
         │
         ├─ rules  ──► regex match ─────────────────────────────────┐
         ├─ openai ──► GPT-4o-mini (JSON response) ────────────────┤
         ├─ claude ──► Claude Haiku (JSON response) ───────────────┤
         ├─ gemini ──► Gemini Flash (JSON response) ───────────────┤
         ├─ local  ──► Ollama HTTP API ──────────────────────────── ┤
         └─ hf     ──► transformers pipeline (on-device) ──────────┘
                                                                    │
                                                                    ▼
                                                    { tool: "list_materials",
                                                      args: { formula: "Si" } }
                                                                    │
                                                                    ▼
                                                    Python code generation
                                                                    │
                                                                    ▼
         endpoint.list({"formula": "Si", "owner._id": OWNER_ID})
                                                                    │
                                                                    ▼
                                        GET https://platform.mat3ra.com/api/2018-10-01/materials
                                            ?formula=Si&owner._id=<ACCOUNT_ID>
                                            Authorization: Bearer <AUTH_TOKEN>
```
