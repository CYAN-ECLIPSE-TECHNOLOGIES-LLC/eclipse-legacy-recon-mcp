#!/usr/bin/env python3
# Eclipse Legacy Recon MCP
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
# Schema-enumerating fuzz over wire input parsing — no -32603 escapes.

"""Hardening: enumerate wrong-typed values for every tool param
through server.handle; all must be named -32602 or isError named
refusals, never -32603 / raw exception text. Engine-level fuzz too."""
import itertools
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))
import recon_engine as eng  # noqa: E402
import server  # noqa: E402

FIX = str(HERE / "fixtures" / "legacy-tree")
BAD = [None, True, False, 0, -1, 3.5, "x", "", [], ["a"], {}, {"a": 1},
       b"bytes", 10**30]


def wire(name, args, rid=1):
    return server.handle({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                          "params": {"name": name, "arguments": args}})


class WireFuzz(unittest.TestCase):
    def test_schema_enumerated_fuzz(self):
        cases = 0
        for tool in server.TOOLS:
            for field in ("path", "max_files"):
                for bad in BAD:
                    args = {"path": FIX, "max_files": 10}
                    args[field] = bad
                    resp = wire(tool, args, rid=cases)
                    cases += 1
                    self.assertIsNotNone(resp)
                    err = resp.get("error", {})
                    self.assertNotEqual(err.get("code"), -32603,
                                        (tool, field, bad, resp))
                    if "result" in resp:
                        txt = resp["result"]["content"][0]["text"]
                        payload = json.loads(txt)
                        if resp["result"].get("isError"):
                            self.assertIn("error", payload)
        self.assertGreater(cases, 100)

    def test_missing_and_unknown(self):
        for tool in server.TOOLS:
            resp = wire(tool, {})
            self.assertEqual(resp["error"]["code"], -32602)
        resp = wire("nope_tool", {"path": FIX})
        self.assertEqual(resp["error"]["code"], -32602)
        for forbidden in server.FORBIDDEN_TOOL_NAMES:
            resp = wire(forbidden, {"path": FIX})
            self.assertEqual(resp["error"]["code"], -32602, forbidden)

    def test_non_dict_args_and_params(self):
        for bad in BAD:
            resp = server.handle({"jsonrpc": "2.0", "id": 9,
                                  "method": "tools/call",
                                  "params": {"name": "recon_scan",
                                             "arguments": bad}})
            if isinstance(bad, dict):
                continue  # dict args handled by schema/refusal path
            self.assertNotEqual(resp.get("error", {}).get("code"), -32603, bad)
        resp = server.handle({"jsonrpc": "2.0", "id": 9,
                              "method": "tools/call", "params": ["x"]})
        self.assertEqual(resp["error"]["code"], -32602)

    def test_tools_list_exact(self):
        resp = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {t["name"] for t in resp["result"]["tools"]}
        self.assertEqual(names, {"recon_scan", "architecture_map",
                                 "dependency_risk_list", "modernization_inputs"})
        for t in resp["result"]["tools"]:
            self.assertIn("Read-only", t["description"])


class EngineFuzz(unittest.TestCase):
    def test_coerce_int_param(self):
        self.assertEqual(eng.coerce_int_param(5, "x", "R"), 5)
        self.assertEqual(eng.coerce_int_param("42", "x", "R"), 42)
        self.assertEqual(eng.coerce_int_param(2.0, "x", "R"), 2)
        for bad in (True, False, "abc", 2.5, [], {}, None, b"1"):
            with self.assertRaises(eng.ToolError) as c:
                eng.coerce_int_param(bad, "max_files", "MAX_FILES_INVALID")
            self.assertIn("MAX_FILES_INVALID", str(c.exception))

    def test_max_files_bounds(self):
        for bad in (0, -5, 10**9, "99999999"):
            with self.assertRaises(eng.ToolError) as c:
                eng.scan_target({"path": FIX, "max_files": bad})
            self.assertIn("MAX_FILES_INVALID", str(c.exception))

    def test_scan_target_arg_shapes(self):
        for bad in BAD:
            with self.assertRaises(eng.ToolError):
                eng.scan_target(bad if isinstance(bad, dict) else {"path": bad})


if __name__ == "__main__":
    unittest.main()

# Eclipse Legacy Recon MCP · © 2026 Cyan Eclipse Technologies LLC · cetech.ai
