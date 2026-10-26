#!/usr/bin/env python3
# Eclipse Legacy Recon MCP
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
# MCP-over-stdio server — read-only legacy codebase recon tools.

"""Eclipse Legacy Recon MCP — v0.1.0 server (MCP over stdio).

Powered by Cyan Eclipse Technologies (cetech.ai).
Read-only: tools scan a caller-supplied local directory and
return reports at the narrowed observed scope in CLAIM-SCOPE.md.
No writes, no execution of target code, no network. Named
refusals, fail-closed.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import recon_engine as eng  # noqa: E402
from recon_engine import ToolError  # noqa: E402

TOOLS = {
    "recon_scan": (
        lambda args: eng.scan_target(args),
        "Narrowed-scope recon of a local codebase directory: "
        "architecture map + dependency/EOL risks + "
        "modernization-estimate inputs, in one scoped report. "
        "Read-only; never executes target code. " + eng.DESCRIPTOR,
        {"path": {"type": "string"},
         "max_files": {"type": "integer"}},
        ["path"]),
    "architecture_map": (
        eng.architecture_map,
        "Architecture map only, at the narrowed observed scope: "
        "languages, module/package structure, entry points, "
        "layering signals, file/size distribution, with the "
        "evidence recorded by the engine. " + eng.DESCRIPTOR,
        {"path": {"type": "string"},
         "max_files": {"type": "integer"}},
        ["path"]),
    "dependency_risk_list": (
        eng.dependency_risk_list,
        "Scoped dependency inventory (DECLARED / OBSERVED / "
        "INFERRED, kept separate; OBSERVED is positive and "
        "non-exhaustive) + EOL/unpinned risk list. Each EOL entry "
        "cites its rule id from the versioned rules table. "
        + eng.DESCRIPTOR,
        {"path": {"type": "string"},
         "max_files": {"type": "integer"}},
        ["path"]),
    "modernization_inputs": (
        eng.modernization_inputs,
        "Modernization estimate INPUTS only (LOC by language, "
        "test presence/ratio, manifest age signals, coupling "
        "hotspots by fan-in) — raw inputs, NOT an estimate. "
        + eng.DESCRIPTOR,
        {"path": {"type": "string"},
         "max_files": {"type": "integer"}},
        ["path"]),
}

FORBIDDEN_TOOL_NAMES = {
    "execute", "run", "import_code", "eval", "shell", "write",
    "delete", "modify", "fix", "upgrade", "install", "download",
    "fetch", "deploy",
}

_SCHEMA_TYPES = {"string": (str, "a string"),
                 "integer": (int, "an integer"),
                 "object": (dict, "an object")}


def tool_list():
    return [{"name": n, "description": d,
             "inputSchema": {"type": "object", "properties": p,
                             "required": r}}
            for n, (_, d, p, r) in TOOLS.items()]


def validate_args(name, args):
    _, _, props, required = TOOLS[name]
    if not isinstance(args, dict):
        return {"code": -32602, "message": "arguments must be an object"}
    missing = [k for k in required if k not in args]
    if missing:
        return {"code": -32602,
                "message": "missing required argument(s): " + ", ".join(missing)}
    for field, value in args.items():
        spec = props.get(field)
        if spec is None or value is None:
            continue
        expected = _SCHEMA_TYPES.get(spec.get("type"))
        if expected is not None:
            # bool is an int subclass — refuse it for integer fields
            if spec.get("type") == "integer" and isinstance(value, bool):
                return {"code": -32602,
                        "message": f"invalid argument type: {field} must be an integer, got bool"}
            if not isinstance(value, expected[0]):
                # int-shaped strings / integral floats are handled
                # by the engine's coerce_int_param guard, not here
                if spec.get("type") == "integer" and isinstance(value, (str, float)):
                    continue
                return {"code": -32602,
                        "message": f"invalid argument type: {field} must be {expected[1]}, got {type(value).__name__}"}
    return None


def handle(req):
    method, rid = req.get("method", ""), req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": req.get("params", {}).get(
                "protocolVersion", "2025-03-26"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "eclipse-legacy-recon",
                           "version": "0.1.0",
                           "descriptor": eng.DESCRIPTOR,
                           "claim_scope": eng.CLAIM_SCOPE}}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": tool_list()}}
    if method == "tools/call":
        params = req.get("params")
        if not isinstance(params, dict):
            return {"jsonrpc": "2.0", "id": rid, "error": {
                "code": -32602, "message": "params must be an object"}}
        name = params.get("name")
        args = params.get("arguments", {})
        if not isinstance(name, str) or name in FORBIDDEN_TOOL_NAMES \
                or name not in TOOLS:
            return {"jsonrpc": "2.0", "id": rid, "error": {
                "code": -32602, "message": f"unknown tool: {name}"}}
        schema_error = validate_args(name, args)
        if schema_error is not None:
            return {"jsonrpc": "2.0", "id": rid, "error": schema_error}
        try:
            out = TOOLS[name][0](args)
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": json.dumps(out, indent=1)}]}}
        except ToolError as exc:
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text",
                             "text": json.dumps({"error": str(exc)})}],
                "isError": True}}
    if rid is not None:
        return {"jsonrpc": "2.0", "id": rid, "error": {
            "code": -32601, "message": f"method not found: {method}"}}
    return None


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            response = handle(json.loads(line))
        except Exception as exc:  # never crash the transport
            response = {"jsonrpc": "2.0", "id": None, "error": {
                "code": -32603, "message": str(exc)}}
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()

# Eclipse Legacy Recon MCP · © 2026 Cyan Eclipse Technologies LLC · cetech.ai
