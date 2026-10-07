"""
Mat3ra MCP Server – proof of concept
=====================================
Exposes a handful of Mat3ra API operations as MCP tools so that any
MCP-compatible client (Claude Desktop, Cursor, etc.) can call them.

Tools
-----
* list_materials        – search materials by formula or free-form query
* get_material          – fetch a single material by ID
* create_material       – create a new material from a JSON config
* list_workflows        – search workflows
* list_jobs             – search jobs
* create_and_submit_job – create + immediately submit a job
* get_job               – fetch a single job by ID

Authentication
--------------
Set the following environment variables before starting the server
(or copy them from examples/config/settings.json):

    MAT3RA_ACCOUNT_ID=<your account id>
    MAT3RA_AUTH_TOKEN=<your auth token>

Optional:
    MAT3RA_ORGANIZATION_ID=<org id>   # use org account instead of personal
    MAT3RA_API_HOST=platform.mat3ra.com
    MAT3RA_API_PORT=443
    MAT3RA_API_VERSION=2018-10-01
    MAT3RA_API_SECURE=true

Running
-------
    # install deps once (inside a venv)
    pip install mcp mat3ra-api-client

    # start the server (stdio transport – default for MCP)
    python mcp_server/server.py

    # or with the MCP CLI
    mcp run mcp_server/server.py
"""

from __future__ import annotations

import json
import os
import sys

# ---------------------------------------------------------------------------
# MCP SDK – https://github.com/modelcontextprotocol/python-sdk
# ---------------------------------------------------------------------------
try:
    import mcp.server.stdio
    from mcp.server import NotificationOptions, Server
    from mcp.server.models import InitializationOptions
    from mcp.types import TextContent, Tool
except ImportError:
    sys.exit(
        "The 'mcp' package is not installed.\n"
        "Run:  pip install mcp mat3ra-api-client\n"
    )

# ---------------------------------------------------------------------------
# Mat3ra API client
# ---------------------------------------------------------------------------
try:
    from mat3ra.api_client.endpoints.jobs import JobEndpoints
    from mat3ra.api_client.endpoints.materials import MaterialEndpoints
    from mat3ra.api_client.endpoints.workflows import WorkflowEndpoints
except ImportError:
    sys.exit(
        "The 'mat3ra-api-client' package is not installed.\n"
        "Run:  pip install mcp mat3ra-api-client\n"
    )

# ---------------------------------------------------------------------------
# Read credentials from environment (fall back to empty string so the error
# surfaces at call time, not at server start-up).
# ---------------------------------------------------------------------------
ACCOUNT_ID = os.environ.get("MAT3RA_ACCOUNT_ID", "")
AUTH_TOKEN = os.environ.get("MAT3RA_AUTH_TOKEN", "")
ORGANIZATION_ID = os.environ.get("MAT3RA_ORGANIZATION_ID", "")
HOST = os.environ.get("MAT3RA_API_HOST", "platform.mat3ra.com")
PORT = int(os.environ.get("MAT3RA_API_PORT", "443"))
VERSION = os.environ.get("MAT3RA_API_VERSION", "2018-10-01")
SECURE = os.environ.get("MAT3RA_API_SECURE", "true").lower() != "false"

ENDPOINT_ARGS = [HOST, PORT, ACCOUNT_ID, AUTH_TOKEN, VERSION, SECURE]

# Owner ID: prefer org, fall back to personal account
OWNER_ID = ORGANIZATION_ID or ACCOUNT_ID


def _endpoint_args() -> list:
    """Return endpoint args, re-reading env vars at call time so the server
    can be started before credentials are set (useful during development)."""
    account_id = os.environ.get("MAT3RA_ACCOUNT_ID", ACCOUNT_ID)
    auth_token = os.environ.get("MAT3RA_AUTH_TOKEN", AUTH_TOKEN)
    return [HOST, PORT, account_id, auth_token, VERSION, SECURE]


def _owner() -> str:
    org = os.environ.get("MAT3RA_ORGANIZATION_ID", ORGANIZATION_ID)
    account = os.environ.get("MAT3RA_ACCOUNT_ID", ACCOUNT_ID)
    return org or account


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _json(obj) -> str:
    return json.dumps(obj, indent=2, default=str)


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
server = Server("mat3ra-mcp")


# ── Tool catalogue ──────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_materials",
            description=(
                "Search materials in the Mat3ra account. "
                "Pass a 'formula' key to filter by chemical formula (e.g. 'Si', 'GaAs'). "
                "Any additional key-value pairs are forwarded directly to the Mongo-style query."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "formula": {
                        "type": "string",
                        "description": "Chemical formula to search for, e.g. 'Si' or 'GaAs'.",
                    },
                    "query": {
                        "type": "object",
                        "description": "Additional Mongo-style query fields (optional).",
                    },
                },
            },
        ),
        Tool(
            name="get_material",
            description="Fetch a single material by its Mat3ra ID.",
            inputSchema={
                "type": "object",
                "required": ["material_id"],
                "properties": {
                    "material_id": {
                        "type": "string",
                        "description": "The _id of the material.",
                    }
                },
            },
        ),
        Tool(
            name="create_material",
            description=(
                "Create a new material on Mat3ra. "
                "Provide a JSON config following https://docs.mat3ra.com/materials/data/."
            ),
            inputSchema={
                "type": "object",
                "required": ["config"],
                "properties": {
                    "config": {
                        "type": "object",
                        "description": "Material config JSON (name, basis, lattice, tags, …).",
                    }
                },
            },
        ),
        Tool(
            name="list_workflows",
            description="List workflows in the Mat3ra account.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "object",
                        "description": "Optional Mongo-style query filter.",
                    }
                },
            },
        ),
        Tool(
            name="list_jobs",
            description="List jobs in the Mat3ra account.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "object",
                        "description": "Optional Mongo-style query filter.",
                    }
                },
            },
        ),
        Tool(
            name="create_and_submit_job",
            description=(
                "Create and immediately submit a calculation job on Mat3ra. "
                "Requires a material_id and a workflow_id."
            ),
            inputSchema={
                "type": "object",
                "required": ["material_id", "workflow_id"],
                "properties": {
                    "material_id": {
                        "type": "string",
                        "description": "The _id of the material to use.",
                    },
                    "workflow_id": {
                        "type": "string",
                        "description": "The _id of the workflow to use.",
                    },
                    "job_name": {
                        "type": "string",
                        "description": "Human-readable name for the job (optional).",
                    },
                },
            },
        ),
        Tool(
            name="get_job",
            description="Fetch a single job by its Mat3ra ID, including its current status.",
            inputSchema={
                "type": "object",
                "required": ["job_id"],
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The _id of the job.",
                    }
                },
            },
        ),
    ]


# ── Tool handlers ────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await _dispatch(name, arguments)
    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]
    return [TextContent(type="text", text=_json(result))]


async def _dispatch(name: str, args: dict):
    ep = _endpoint_args()
    owner = _owner()

    if name == "list_materials":
        q: dict = args.get("query", {})
        if formula := args.get("formula"):
            q["formula"] = formula
        q.setdefault("owner._id", owner)
        endpoint = MaterialEndpoints(*ep)
        return endpoint.list(q)

    if name == "get_material":
        endpoint = MaterialEndpoints(*ep)
        return endpoint.get(args["material_id"])

    if name == "create_material":
        endpoint = MaterialEndpoints(*ep)
        return endpoint.create(args["config"], owner)

    if name == "list_workflows":
        q = args.get("query", {})
        q.setdefault("owner._id", owner)
        endpoint = WorkflowEndpoints(*ep)
        return endpoint.list(q)

    if name == "list_jobs":
        q = args.get("query", {})
        q.setdefault("owner._id", owner)
        endpoint = JobEndpoints(*ep)
        return endpoint.list(q)

    if name == "create_and_submit_job":
        endpoint = JobEndpoints(*ep)
        config = {
            "owner": {"_id": owner},
            "_material": {"_id": args["material_id"]},
            "workflow": {"_id": args["workflow_id"]},
            "name": args.get("job_name", "MCP Job"),
        }
        job = endpoint.create(config)
        endpoint.submit(job["_id"])
        # re-fetch to include the updated status
        return endpoint.get(job["_id"])

    if name == "get_job":
        endpoint = JobEndpoints(*ep)
        return endpoint.get(args["job_id"])

    raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main():
    import mcp.server.stdio

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mat3ra-mcp",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
