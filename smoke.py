#!/usr/bin/env python3
# Eclipse Legacy Recon MCP
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
# Stdio smoke — spawns the real server and drives recon over the wire.

"""Stdio smoke: initialize, tools/list exact, recon fixture tree
(EOL rules fire, symlink escape reported), named refusals."""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
FIX = HERE / "fixtures" / "legacy-tree"


def call(proc, rid, method, params=None):
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": rid,
                                 "method": method, "params": params or {}}) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())


def tool(proc, rid, name, args):
    return call(proc, rid, "tools/call", {"name": name, "arguments": args})


def result_text(resp):
    return json.loads(resp["result"]["content"][0]["text"])


def main():
    link = FIX / "escape_link"
    if not link.is_symlink():
        link.symlink_to("/etc")
    proc = subprocess.Popen([sys.executable, str(HERE / "server.py")],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            text=True)
    resp = call(proc, 1, "initialize", {"protocolVersion": "2025-03-26"})
    assert resp["result"]["serverInfo"]["name"] == "eclipse-legacy-recon", resp
    resp = call(proc, 2, "tools/list")
    names = {t["name"] for t in resp["result"]["tools"]}
    assert names == {"recon_scan", "architecture_map",
                     "dependency_risk_list", "modernization_inputs"}, names
    resp = tool(proc, 3, "execute", {"path": str(FIX)})
    assert resp["error"]["code"] == -32602, resp  # no execution verb
    resp = tool(proc, 4, "recon_scan", {"path": str(FIX)})
    r = result_text(resp)
    ids = {x.get("rule_id") for x in r["risks"]}
    assert "EOL-PKG-DJANGO32" in ids and "EOL-RT-PY38" in ids, ids
    assert any(s["escape"] for s in r["symlinks"]), r["symlinks"]
    assert r["binary_files_skipped"] >= 1
    assert any(i["name"] == "Pillow" for i in r["dependencies"]["inferred"])
    resp = tool(proc, 5, "recon_scan", {"path": "/no/such/dir-xyz"})
    refused = result_text(resp)
    assert "TARGET_NOT_FOUND" in refused["error"], refused
    resp = tool(proc, 6, "modernization_inputs", {"path": str(FIX)})
    mi = result_text(resp)["modernization_inputs"]
    assert mi["total_loc"] > 0 and "NOT an estimate" in mi["note"], mi
    proc.stdin.close()
    proc.wait(timeout=10)
    print("SMOKE OK — tools/list exact, EOL rules cite ids, symlink "
          "escape reported not traversed, binary skipped, TARGET_NOT_FOUND "
          "named, modernization inputs are inputs not an estimate")


if __name__ == "__main__":
    main()

# Eclipse Legacy Recon MCP · © 2026 Cyan Eclipse Technologies LLC · cetech.ai
