"""
Mat3ra Prompt-to-Code Server
=============================
HTTP server that accepts natural-language prompts and returns
the equivalent Python Mat3ra API code.

POST /ask   {"prompt": "...", "backend": "rules|openai|claude|gemini|local"}
GET  /      browser playground

Run:
    python mcp_server/code_server.py

Environment variables:
    INTENT_BACKEND      default backend (rules)
    OPENAI_API_KEY      required for openai backend
    ANTHROPIC_API_KEY   required for claude backend
    GEMINI_API_KEY      required for gemini backend
    HF_RUNTIME          transformers (default) | ollama
    HF_MODEL            HuggingFace model repo id (default: Qwen/Qwen2.5-1.5B-Instruct)
    HF_DEVICE           cpu | cuda | mps | auto  (default: auto)
    OLLAMA_HOST         Ollama base URL  (default: http://localhost:11434)  [HF_RUNTIME=ollama]
    OLLAMA_MODEL        model name       (default: llama3.2)                [HF_RUNTIME=ollama]
    OPENAI_MODEL        (default: gpt-4o-mini)
    ANTHROPIC_MODEL     (default: claude-3-5-haiku-latest)
    GEMINI_MODEL        (default: gemini-2.0-flash)
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# intent module lives alongside this file
sys.path.insert(0, str(Path(__file__).parent))
from intent import detect_intent  # noqa: E402

# ---------------------------------------------------------------------------
# HTML playground
# ---------------------------------------------------------------------------

HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mat3ra Prompt-to-Code</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #0d1117; color: #c9d1d9;
    font-family: system-ui, -apple-system, sans-serif;
    display: flex; flex-direction: column; align-items: center;
    min-height: 100vh; padding: 48px 16px;
  }
  h1 { font-size: 1.7rem; color: #58a6ff; margin-bottom: 6px; }
  .sub { color: #8b949e; font-size: 0.9rem; margin-bottom: 32px; }
  .card {
    background: #161b22; border: 1px solid #30363d; border-radius: 12px;
    padding: 28px; width: 100%; max-width: 760px;
  }

  /* prompt row */
  .prompt-row { display: flex; gap: 10px; }
  textarea {
    flex: 1; background: #0d1117; color: #c9d1d9;
    border: 1px solid #30363d; border-radius: 8px;
    padding: 12px 14px; font-size: 0.95rem; font-family: inherit;
    resize: vertical; min-height: 64px; outline: none;
    transition: border-color 0.2s;
  }
  textarea:focus { border-color: #58a6ff; }

  /* LLM selector */
  .selector-wrap { display: flex; flex-direction: column; gap: 6px; }
  select {
    background: #0d1117; color: #c9d1d9;
    border: 1px solid #30363d; border-radius: 8px;
    padding: 10px 12px; font-size: 0.85rem; outline: none;
    cursor: pointer; transition: border-color 0.2s;
  }
  select:focus { border-color: #58a6ff; }
  select option { background: #161b22; }
  .sel-label { font-size: 0.7rem; color: #8b949e; text-transform: uppercase;
               letter-spacing: 0.05em; }

  button.gen {
    margin-top: 12px; background: #238636; color: #fff;
    border: none; border-radius: 8px; padding: 11px 26px;
    font-size: 0.95rem; cursor: pointer; transition: background 0.2s;
    width: 100%;
  }
  button.gen:hover { background: #2ea043; }
  button.gen:disabled { background: #21262d; color: #484f58; cursor: default; }

  /* example buttons */
  .examples { margin-top: 18px; display: flex; flex-wrap: wrap; gap: 6px;
              align-items: center; }
  .examples span { color: #8b949e; font-size: 0.8rem; margin-right: 4px; }
  .ex {
    background: none; border: 1px solid #30363d; color: #8b949e;
    border-radius: 6px; padding: 4px 11px; cursor: pointer;
    font-size: 0.8rem; transition: border-color 0.2s, color 0.2s;
  }
  .ex:hover { border-color: #58a6ff; color: #58a6ff; }

  /* result area */
  .label { font-size: 0.72rem; color: #8b949e; text-transform: uppercase;
           letter-spacing: 0.05em; margin: 20px 0 6px; }
  .meta-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
              margin-bottom: 10px; }
  .badge {
    display: inline-block; border-radius: 12px; padding: 3px 11px;
    font-size: 0.75rem; border: 1px solid;
  }
  .badge-tool    { background: #1f6feb22; color: #58a6ff; border-color: #1f6feb; }
  .badge-backend { background: #3fb95022; color: #3fb950; border-color: #3fb950; }
  .badge-error   { background: #f8514922; color: #f85149; border-color: #f85149; }
  pre {
    background: #0d1117; border: 1px solid #30363d; border-radius: 8px;
    padding: 18px; font-size: 0.82rem; line-height: 1.55;
    overflow-x: auto; white-space: pre-wrap; color: #79c0ff;
    min-height: 60px;
  }
  .spinner { display: none; width: 16px; height: 16px; border: 2px solid #30363d;
             border-top-color: #58a6ff; border-radius: 50%;
             animation: spin 0.7s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<h1>Mat3ra Prompt-to-Code</h1>
<p class="sub">Type a plain-English request — get back the Python API code.</p>
<div class="card">

  <div class="prompt-row">
    <textarea id="prompt" placeholder="e.g. List my silicon materials"></textarea>
    <div class="selector-wrap">
      <span class="sel-label">LLM backend</span>
      <select id="backend">
        <option value="rules" selected>Rules (no LLM)</option>
        <option value="openai">OpenAI</option>
        <option value="claude">Claude (Anthropic)</option>
        <option value="gemini">Gemini (Google)</option>
        <option value="hf">HuggingFace local (transformers / Ollama)</option>
      </select>
    </div>
  </div>

  <button class="gen" id="btn" onclick="ask()">
    Generate Code
    <span class="spinner" id="spin"></span>
  </button>

  <div class="examples">
    <span>Try:</span>
    <button class="ex" onclick="fill('List my silicon materials')">List Si materials</button>
    <button class="ex" onclick="fill('Find all GaAs compounds')">Find GaAs</button>
    <button class="ex" onclick="fill('Create a new FCC copper material')">Create material</button>
    <button class="ex" onclick="fill('Show my workflows')">List workflows</button>
    <button class="ex" onclick="fill('Submit a DFT calculation job')">Submit job</button>
    <button class="ex" onclick="fill('Show all my jobs')">List jobs</button>
  </div>

  <div class="label">Result</div>
  <div class="meta-row">
    <span class="badge badge-tool"   id="tool-badge">—</span>
    <span class="badge badge-backend" id="backend-badge">—</span>
    <span class="badge badge-error"  id="err-badge"  style="display:none"></span>
  </div>

  <div class="label">Generated Python code</div>
  <pre id="code">—</pre>

</div>

<script>
const $ = id => document.getElementById(id);

async function ask() {
  const prompt  = $('prompt').value.trim();
  const backend = $('backend').value;
  if (!prompt) return;

  $('btn').disabled = true;
  $('spin').style.display = 'inline-block';
  $('err-badge').style.display = 'none';
  $('code').textContent = '…';

  try {
    const r    = await fetch('/ask', {
      method:  'POST',
      headers: {'Content-Type': 'application/json'},
      body:    JSON.stringify({prompt, backend}),
    });
    const data = await r.json();

    if (data.error) {
      $('tool-badge').textContent    = '—';
      $('backend-badge').textContent = backend;
      $('err-badge').textContent     = data.error;
      $('err-badge').style.display   = 'inline-block';
      $('code').textContent          = '';
    } else {
      $('tool-badge').textContent    = data.tool;
      $('backend-badge').textContent = data.backend;
      $('code').textContent          = data.code;
    }
  } catch (e) {
    $('code').textContent = 'Network error: ' + e.message;
  } finally {
    $('btn').disabled            = false;
    $('spin').style.display      = 'none';
  }
}

function fill(text) {
  $('prompt').value = text;
  ask();
}

$('prompt').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(); }
});
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"  {self.address_string()}  {self.command}  {self.path}"
              f"  →  {fmt % args}")

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", HTML.encode())
        else:
            self._send(404, "text/plain", b"Not found")

    def do_POST(self):
        if self.path != "/ask":
            self._send(404, "text/plain", b"Not found")
            return

        length  = int(self.headers.get("Content-Length", 0))
        body    = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._send(400, "application/json",
                       json.dumps({"error": "invalid JSON"}).encode())
            return

        prompt  = payload.get("prompt", "").strip()
        backend = payload.get("backend", os.environ.get("INTENT_BACKEND", "rules"))

        if not prompt:
            self._send(400, "application/json",
                       json.dumps({"error": "prompt is required"}).encode())
            return

        try:
            intent = detect_intent(prompt, backend)
        except Exception as exc:
            self._send(200, "application/json; charset=utf-8",
                       json.dumps({"error": str(exc)}).encode())
            return

        self._send(200, "application/json; charset=utf-8",
                   json.dumps(intent, indent=2).encode())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    HOST, PORT = "localhost", 8888
    httpd = HTTPServer((HOST, PORT), Handler)
    backend = os.environ.get("INTENT_BACKEND", "rules")
    print(f"\n  Mat3ra Prompt-to-Code server")
    print(f"  Playground  : http://{HOST}:{PORT}/")
    print(f"  API         : POST http://{HOST}:{PORT}/ask")
    print(f"  Default LLM : {backend}")
    print(f"  Backends available: rules (always), openai, claude, gemini, hf")
    print(f"  hf runtime: HF_RUNTIME=transformers (default) | ollama")
    print(f"  Set INTENT_BACKEND=openai (etc.) or select in the UI.")
    print(f"\n  Press Ctrl+C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
