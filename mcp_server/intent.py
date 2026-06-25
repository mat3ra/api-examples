"""
intent.py – prompt → Mat3ra API intent detection
==================================================
Supports six backends, selected via the INTENT_BACKEND env var
or the `backend` argument passed at call time:

  rules   no deps, keyword matching (default / fallback)
  openai  requires: pip install openai          + OPENAI_API_KEY
  claude  requires: pip install anthropic        + ANTHROPIC_API_KEY
  gemini  requires: pip install google-genai     + GEMINI_API_KEY
  hf      local open-source model — two runtimes (set via HF_RUNTIME):
          transformers  run a model in-process via HuggingFace Transformers (default)
                        pip install transformers accelerate torch
                        HF_MODEL  (default: Qwen/Qwen2.5-1.5B-Instruct)
                        HF_DEVICE (default: auto)
          ollama        delegate to a running Ollama server (serves HF/GGUF models)
                        requires: Ollama running on OLLAMA_HOST (default: localhost:11434)
                        OLLAMA_MODEL (default: llama3.2)

All backends return the same dict:
  {
    "tool":   str,   # one of the 7 tool names
    "args":   dict,  # tool arguments (minus owner._id which is added later)
    "module": str,   # python module name  e.g. "materials"
    "cls":    str,   # endpoint class name e.g. "MaterialEndpoints"
    "call":   str,   # python code snippet for the API call
  }
"""

from __future__ import annotations

import json
import os
import re
import textwrap
import urllib.error
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# Tool catalogue – drives both code generation and the LLM system prompt
# ---------------------------------------------------------------------------

TOOLS: dict[str, dict[str, Any]] = {
    "list_materials": {
        "module": "materials", "cls": "MaterialEndpoints",
        "description": "Search / list materials by formula or Mongo query.",
        "args_schema": {"formula": "chemical formula e.g. Si, GaAs (optional)"},
    },
    "get_material": {
        "module": "materials", "cls": "MaterialEndpoints",
        "description": "Fetch a single material by its 24-char hex _id.",
        "args_schema": {"material_id": "24-char hex string"},
    },
    "create_material": {
        "module": "materials", "cls": "MaterialEndpoints",
        "description": "Create a new material from a JSON config.",
        "args_schema": {},
    },
    "list_workflows": {
        "module": "workflows", "cls": "WorkflowEndpoints",
        "description": "List workflows in the account.",
        "args_schema": {},
    },
    "list_jobs": {
        "module": "jobs", "cls": "JobEndpoints",
        "description": "List calculation jobs in the account.",
        "args_schema": {},
    },
    "create_and_submit_job": {
        "module": "jobs", "cls": "JobEndpoints",
        "description": "Create and immediately submit a calculation job.",
        "args_schema": {
            "material_id": "24-char hex _id of the material",
            "workflow_id": "24-char hex _id of the workflow",
            "job_name": "optional human-readable name",
        },
    },
    "get_job": {
        "module": "jobs", "cls": "JobEndpoints",
        "description": "Fetch a job and its current status by _id.",
        "args_schema": {"job_id": "24-char hex string"},
    },
}

# ---------------------------------------------------------------------------
# System prompt shared by all LLM backends
# ---------------------------------------------------------------------------

_TOOL_DESCRIPTIONS = "\n".join(
    f"  - {name}({', '.join(k for k in meta['args_schema'])})"
    f"  # {meta['description']}"
    for name, meta in TOOLS.items()
)

SYSTEM_PROMPT = f"""\
You are a Mat3ra materials-science API assistant.

Given a natural-language request, identify which Mat3ra API tool to call \
and what arguments to pass.

Available tools:
{_TOOL_DESCRIPTIONS}

Rules:
- Extract chemical formulas from the text (e.g. "silicon" → "Si", "GaAs" → "GaAs").
- If an ID-like string appears (24 hex chars), use it as material_id / job_id.
- If the intent is unclear, default to list_materials with no formula.

Respond ONLY with a single JSON object, no markdown fences, no explanation:
{{
  "tool": "<tool_name>",
  "args": {{ ... }}
}}

Examples:
  "List my silicon materials"   → {{"tool":"list_materials","args":{{"formula":"Si"}}}}
  "Find GaAs compounds"         → {{"tool":"list_materials","args":{{"formula":"GaAs"}}}}
  "Create a copper FCC crystal" → {{"tool":"create_material","args":{{}}}}
  "Show my workflows"           → {{"tool":"list_workflows","args":{{}}}}
  "Submit a DFT job"            → {{"tool":"create_and_submit_job","args":{{"material_id":"<material_id>","workflow_id":"<workflow_id>"}}}}
  "Check job 507f1f77bcf86cd799439011" → {{"tool":"get_job","args":{{"job_id":"507f1f77bcf86cd799439011"}}}}
"""

# ---------------------------------------------------------------------------
# Code generation from a resolved (tool, args) pair
# ---------------------------------------------------------------------------

BOILERPLATE = """\
import os
from mat3ra.api_client.endpoints.{module} import {cls}

ACCOUNT_ID = os.environ["MAT3RA_ACCOUNT_ID"]
AUTH_TOKEN  = os.environ["MAT3RA_AUTH_TOKEN"]
OWNER_ID    = os.environ.get("MAT3RA_ORGANIZATION_ID") or ACCOUNT_ID

endpoint = {cls}(
    "platform.mat3ra.com", 443,
    ACCOUNT_ID, AUTH_TOKEN,
    "2018-10-01", secure=True
)
"""


def _build_call(tool: str, args: dict) -> str:
    """Generate the Python call snippet for a given tool + args."""
    if tool == "list_materials":
        query: dict = {"owner._id": "OWNER_ID"}
        if f := args.get("formula"):
            query["formula"] = f
        q = json.dumps(query, indent=4).replace('"OWNER_ID"', "OWNER_ID")
        return f"materials = endpoint.list(\n    {q}\n)"

    if tool == "get_material":
        mid = args.get("material_id", "<material_id>")
        return f'material = endpoint.get("{mid}")'

    if tool == "create_material":
        return textwrap.dedent("""\
            config = {
                "name": "My Material",
                "basis": {
                    "elements":    [{"id": 1, "value": "Si"}, {"id": 2, "value": "Si"}],
                    "coordinates": [{"id": 1, "value": [0, 0, 0]},
                                    {"id": 2, "value": [0.25, 0.25, 0.25]}],
                    "units": "crystal",
                },
                "lattice": {
                    "type": "FCC", "a": 3.867, "b": 3.867, "c": 3.867,
                    "alpha": 60, "beta": 60, "gamma": 60,
                    "units": {"length": "angstrom", "angle": "degree"},
                },
                "tags": ["MCP"],
            }
            material = endpoint.create(config, OWNER_ID)""")

    if tool == "list_workflows":
        return 'workflows = endpoint.list({"owner._id": OWNER_ID})'

    if tool == "list_jobs":
        return 'jobs = endpoint.list({"owner._id": OWNER_ID})'

    if tool == "create_and_submit_job":
        mid = args.get("material_id", "<material_id>")
        wid = args.get("workflow_id", "<workflow_id>")
        name = args.get("job_name", "MCP Job")
        return textwrap.dedent(f"""\
            config = {{
                "owner":     {{"_id": OWNER_ID}},
                "_material": {{"_id": "{mid}"}},
                "workflow":  {{"_id": "{wid}"}},
                "name":      "{name}",
            }}
            job = endpoint.create(config)
            endpoint.submit(job["_id"])
            job = endpoint.get(job["_id"])   # re-fetch to see updated status""")

    if tool == "get_job":
        jid = args.get("job_id", "<job_id>")
        return f'job = endpoint.get("{jid}")'

    return f"# Unknown tool: {tool}"


def build_intent(tool: str, args: dict, backend: str = "rules") -> dict:
    """Assemble the full intent dict from an (tool, args) pair."""
    if tool not in TOOLS:
        tool = "list_materials"
        args = {}
    meta = TOOLS[tool]
    call = _build_call(tool, args)
    code = BOILERPLATE.format(module=meta["module"], cls=meta["cls"]).rstrip()
    code += "\n\n" + call + "\n"
    return {
        "tool":    tool,
        "args":    {k: v for k, v in args.items() if k != "owner._id"},
        "module":  meta["module"],
        "cls":     meta["cls"],
        "call":    call,
        "code":    code,
        "backend": backend,
    }


def _parse_llm_json(text: str) -> tuple[str, dict]:
    """
    Extract tool + args from raw LLM output.
    Strips markdown fences if present.
    """
    # strip ```json ... ``` fences
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    # find first {...}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON object found in LLM response: {text!r}")
    data = json.loads(m.group())
    return data.get("tool", "list_materials"), data.get("args", {})


# ---------------------------------------------------------------------------
# Rule-based backend (no deps)
# ---------------------------------------------------------------------------

def _rules(prompt: str) -> tuple[str, dict]:
    p = prompt.lower()
    fm = re.search(r"\b([A-Z][a-z]?(?:\d*[A-Z][a-z]?)*\d*)\b", prompt)
    formula = fm.group(1) if fm else None
    junk = {"List", "Show", "Find", "Get", "Create", "Submit", "Check", "Run"}

    if re.search(r"\b(list|search|find|get|show)\b.*\bmaterial", p):
        args: dict = {}
        if formula and formula not in junk:
            args["formula"] = formula
        return "list_materials", args

    if re.search(r"\b(create|add|upload|make)\b.*\bmaterial", p):
        return "create_material", {}

    if re.search(r"\bget\b.*\bmaterial", p):
        id_m = re.search(r"\b([a-f0-9]{24})\b", prompt)
        return "get_material", {"material_id": id_m.group(1) if id_m else "<material_id>"}

    if re.search(r"\b(list|search|find|show)\b.*\bworkflow", p):
        return "list_workflows", {}

    if re.search(r"\b(list|search|find|show)\b.*\bjob", p):
        return "list_jobs", {}

    if re.search(r"\b(create|submit|run|launch)\b.*\bjob", p):
        return "create_and_submit_job", {
            "material_id": "<material_id>",
            "workflow_id": "<workflow_id>",
        }

    if re.search(r"\b(get|status|check)\b.*\bjob", p):
        id_m = re.search(r"\b([a-f0-9]{24})\b", prompt)
        return "get_job", {"job_id": id_m.group(1) if id_m else "<job_id>"}

    # default
    args2: dict = {}
    if formula and formula not in junk:
        args2["formula"] = formula
    return "list_materials", args2


# ---------------------------------------------------------------------------
# OpenAI backend
# ---------------------------------------------------------------------------

def _openai(prompt: str) -> tuple[str, dict]:
    try:
        import openai  # noqa: PLC0415
    except ImportError:
        raise RuntimeError("pip install openai")

    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model  = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    resp   = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        temperature=0,
    )
    return _parse_llm_json(resp.choices[0].message.content or "")


# ---------------------------------------------------------------------------
# Anthropic / Claude backend
# ---------------------------------------------------------------------------

def _claude(prompt: str) -> tuple[str, dict]:
    try:
        import anthropic  # noqa: PLC0415
    except ImportError:
        raise RuntimeError("pip install anthropic")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model  = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
    msg    = client.messages.create(
        model=model,
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_llm_json(msg.content[0].text)


# ---------------------------------------------------------------------------
# Google Gemini backend
# ---------------------------------------------------------------------------

def _gemini(prompt: str) -> tuple[str, dict]:
    try:
        from google import genai  # noqa: PLC0415
    except ImportError:
        raise RuntimeError("pip install google-genai")

    api_key = os.environ["GEMINI_API_KEY"]
    model   = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    client  = genai.Client(api_key=api_key)
    resp    = client.models.generate_content(
        model=model,
        contents=SYSTEM_PROMPT + "\n\nUser request: " + prompt,
    )
    return _parse_llm_json(resp.text)


# ---------------------------------------------------------------------------
# Local / Ollama backend
# ---------------------------------------------------------------------------

def _local(prompt: str) -> tuple[str, dict]:
    host  = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    full_prompt = SYSTEM_PROMPT + "\n\nUser request: " + prompt

    payload = json.dumps({
        "model":  model,
        "prompt": full_prompt,
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        f"{host}/api/generate",
        data    = payload,
        headers = {"Content-Type": "application/json"},
        method  = "POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Cannot reach Ollama at {host}. "
            f"Is it running? (ollama serve)  Error: {e}"
        )
    return _parse_llm_json(data.get("response", ""))


# ---------------------------------------------------------------------------
# HuggingFace backend — two runtimes selected by HF_RUNTIME env var
# ---------------------------------------------------------------------------
#   transformers  in-process HuggingFace Transformers pipeline (default)
#   ollama        HTTP call to a local Ollama server (serves HF/GGUF models)
# ---------------------------------------------------------------------------

# Pipeline cache for the transformers runtime (loaded once per server process).
_hf_pipeline_cache: dict = {}


def _hf_ollama(prompt: str) -> tuple[str, dict]:
    """HuggingFace via Ollama — Ollama is a local server that serves HF-compatible
    (GGUF) models.  No Python dependencies beyond stdlib urllib."""
    host  = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    full_prompt = SYSTEM_PROMPT + "\n\nUser request: " + prompt

    payload = json.dumps({
        "model":  model,
        "prompt": full_prompt,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{host}/api/generate",
        data    = payload,
        headers = {"Content-Type": "application/json"},
        method  = "POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Cannot reach Ollama at {host}.  Is it running?  (ollama serve)\n"
            f"Set OLLAMA_HOST if it is on a different address.  Error: {e}"
        )
    return _parse_llm_json(data.get("response", ""))


def _hf_transformers(prompt: str) -> tuple[str, dict]:
    """HuggingFace via Transformers — runs the model in-process.

    Recommended small models (auto-downloaded on first use):
      Qwen/Qwen2.5-0.5B-Instruct         ~1 GB  fastest, any CPU
      Qwen/Qwen2.5-1.5B-Instruct         ~3 GB  default, good balance
      HuggingFaceTB/SmolLM2-1.7B-Instruct ~3 GB  very capable for size
      microsoft/Phi-3-mini-4k-instruct    ~8 GB  high quality

    Env vars:
      HF_MODEL   model repo id  (default: Qwen/Qwen2.5-1.5B-Instruct)
      HF_DEVICE  cpu | cuda | mps | auto  (default: auto)
    """
    try:
        from transformers import pipeline as hf_pipeline  # noqa: PLC0415
    except ImportError:
        raise RuntimeError(
            "pip install transformers accelerate\n"
            "Mac (Apple Silicon / CPU): pip install torch\n"
            "Linux (CUDA):              pip install torch "
            "--index-url https://download.pytorch.org/whl/cu121"
        )

    model_id  = os.environ.get("HF_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
    device    = os.environ.get("HF_DEVICE", "auto")
    cache_key = (model_id, device)

    if cache_key not in _hf_pipeline_cache:
        print(f"[hf] Loading {model_id} on device={device} … (one-time download/load)")
        _hf_pipeline_cache[cache_key] = hf_pipeline(
            "text-generation",
            model       = model_id,
            device_map  = device,
            torch_dtype = "auto",
        )
        print(f"[hf] {model_id} ready.")

    pipe     = _hf_pipeline_cache[cache_key]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]
    try:
        result = pipe(messages, max_new_tokens=256, do_sample=False,
                      return_full_text=False)
        text = result[0]["generated_text"]
        if isinstance(text, list):          # some pipelines return message list
            text = text[-1].get("content", "")
    except Exception:
        full   = SYSTEM_PROMPT + "\n\nUser request: " + prompt
        result = pipe(full, max_new_tokens=256, do_sample=False,
                      return_full_text=False)
        text   = result[0]["generated_text"]
    return _parse_llm_json(text)


def _huggingface(prompt: str) -> tuple[str, dict]:
    """Dispatch to the correct HF runtime based on HF_RUNTIME env var."""
    runtime = os.environ.get("HF_RUNTIME", "transformers").lower()
    if runtime == "ollama":
        return _hf_ollama(prompt)
    if runtime == "transformers":
        return _hf_transformers(prompt)
    raise ValueError(
        f"Unknown HF_RUNTIME={runtime!r}.  Choose 'transformers' or 'ollama'."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_BACKENDS = {
    "rules":  _rules,
    "openai": _openai,
    "claude": _claude,
    "gemini": _gemini,
    "hf":     _huggingface,
}

DEFAULT_BACKEND = os.environ.get("INTENT_BACKEND", "rules")


def detect_intent(prompt: str, backend: str | None = None) -> dict:
    """
    Detect the Mat3ra API intent from a natural-language prompt.

    Args:
        prompt:  user text
        backend: "rules" | "openai" | "claude" | "gemini" | "hf"
                 Defaults to INTENT_BACKEND env var, then "rules".

    Returns:
        Intent dict with keys: tool, args, module, cls, call, code, backend
    """
    backend = (backend or DEFAULT_BACKEND).lower()
    if backend not in _BACKENDS:
        raise ValueError(f"Unknown backend {backend!r}. Choose from: {list(_BACKENDS)}")

    fn = _BACKENDS[backend]
    try:
        tool, args = fn(prompt)
    except Exception as exc:
        if backend != "rules":
            # graceful fallback to rules on any LLM error
            print(f"[intent] {backend} failed ({exc}), falling back to rules")
            tool, args = _rules(prompt)
            backend = f"rules (fallback from {backend})"
        else:
            raise

    return build_intent(tool, args, backend)
