#!/usr/bin/env python3
# Eclipse Legacy Recon MCP
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
# Claims lint for the 2026-10-26 narrowed observed scope.

"""Pin the narrowed claim set mechanically.

The withdrawn machine names may appear in the canonical withdrawn
list, the engine/manifest ``withdrawn`` arrays, and the identified
withdrawn prose. They must not appear in supported lists or in
runtime claim positions (descriptor / tool descriptions).
"""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))
import recon_engine as eng  # noqa: E402
import server  # noqa: E402

FIX = HERE / "fixtures" / "legacy-tree"
README = (HERE / "README.md").read_text(encoding="utf-8")
SCOPE_DOC = (HERE / "CLAIM-SCOPE.md").read_text(encoding="utf-8")
MANIFEST = json.loads(
    (HERE / "bazaar-manifest.json").read_text(encoding="utf-8"))

WITHDRAWN_NAMES = [x["name"] for x in eng.CLAIM_SCOPE["withdrawn"]]
WITHDRAWN_IDS = [x["id"] for x in eng.CLAIM_SCOPE["withdrawn"]]
FORMER_UNIVERSAL_PHRASES = [
    "Every claim cites its evidence",
    "Every claim cites a file path",
]


class NarrowedDescriptor(unittest.TestCase):
    def test_descriptor_names_the_narrowed_scope(self):
        self.assertIn("NARROWED OBSERVED SCOPE", eng.DESCRIPTOR)
        self.assertIn("CLAIM-SCOPE.md", eng.DESCRIPTOR)
        self.assertIn("not an exhaustive or universal JS/TS claim",
                      eng.DESCRIPTOR)
        for phrase in FORMER_UNIVERSAL_PHRASES:
            self.assertNotIn(phrase, eng.DESCRIPTOR)

    def test_all_tool_descriptions_carry_the_scope(self):
        tools = server.tool_list()
        self.assertEqual(len(tools), 4)
        for tool in tools:
            self.assertIn("NARROWED OBSERVED SCOPE",
                          tool["description"], tool["name"])
            self.assertIn("CLAIM-SCOPE.md", tool["description"],
                          tool["name"])
            for name in WITHDRAWN_NAMES:
                self.assertNotIn(name, tool["description"],
                                 tool["name"])


class ClaimScopeObject(unittest.TestCase):
    def test_scope_object_shape_and_ids(self):
        scope = eng.CLAIM_SCOPE
        self.assertEqual(scope["status"],
                         "NARROWED_TO_OBSERVED_SCOPE")
        self.assertEqual(scope["document"], "CLAIM-SCOPE.md")
        self.assertEqual(WITHDRAWN_IDS,
                         ["W%d" % i for i in range(1, 10)])
        self.assertIn(
            "JS_TS_MULTILINE_BLOCK_COMMENT_CONTINUATION_AFTER_SPLIT_NO_CLOSE_SPAN",
            WITHDRAWN_NAMES)
        self.assertIn(
            "JS_TS_CHAINED_NO_CLOSING_SLASH_REGEX_SPANS_ON_ONE_LINE",
            WITHDRAWN_NAMES)
        for name in WITHDRAWN_NAMES:
            self.assertNotIn(name, scope["supported"])

    def test_all_four_outputs_carry_the_same_scope(self):
        args = {"path": str(FIX)}
        outputs = [
            eng.scan_target(args),
            eng.architecture_map(args),
            eng.dependency_risk_list(args),
            eng.modernization_inputs(args),
        ]
        for out in outputs:
            self.assertEqual(out["claim_scope"], eng.CLAIM_SCOPE)
            self.assertEqual(out["descriptor"], eng.DESCRIPTOR)

    def test_initialize_carries_the_scope(self):
        resp = server.handle({"jsonrpc": "2.0", "id": 1,
                              "method": "initialize", "params": {}})
        info = resp["result"]["serverInfo"]
        self.assertEqual(info["claim_scope"], eng.CLAIM_SCOPE)
        self.assertEqual(info["descriptor"], eng.DESCRIPTOR)


class SurfaceAlignment(unittest.TestCase):
    def test_canonical_doc_supported_and_withdrawn_sections(self):
        supported = SCOPE_DOC.split("## Supported claim set", 1)[1] \
            .split("## Withdrawn claims", 1)[0]
        withdrawn = SCOPE_DOC.split("## Withdrawn claims", 1)[1] \
            .split("## Runtime fence choice", 1)[0]
        for wid in WITHDRAWN_IDS:
            self.assertIn("### %s " % wid, withdrawn)
        for name in WITHDRAWN_NAMES:
            self.assertIn(name, withdrawn)
            self.assertNotIn(name, supported)

    def test_readme_names_scope_and_withdrawn_ids(self):
        self.assertIn("CLAIM-SCOPE.md", README)
        self.assertIn("scoped positive inventory", README)
        for wid in WITHDRAWN_IDS:
            self.assertIn("(%s)" % wid, README)
        for name in WITHDRAWN_NAMES:
            self.assertNotIn(name, README)
        for phrase in FORMER_UNIVERSAL_PHRASES:
            self.assertNotIn(phrase, README)

    def test_manifest_scope_matches_engine(self):
        scope = MANIFEST["claim_scope"]
        self.assertEqual(scope["status"], eng.CLAIM_SCOPE["status"])
        self.assertEqual(scope["version"], eng.CLAIM_SCOPE["version"])
        self.assertEqual(scope["document"], eng.CLAIM_SCOPE["document"])
        self.assertEqual(scope["supported"],
                         eng.CLAIM_SCOPE["supported"])
        self.assertEqual(scope["withdrawn"], WITHDRAWN_NAMES)
        for wid in WITHDRAWN_IDS:
            self.assertIn(wid, MANIFEST["description"])
        for phrase in FORMER_UNIVERSAL_PHRASES:
            self.assertNotIn(phrase, MANIFEST["description"])
            self.assertNotIn(phrase, MANIFEST["status"])
            self.assertNotIn(phrase, MANIFEST["tagline"])

    def test_manifest_keeps_the_historical_failed_verdict(self):
        # Narrowing is not a verdict rewrite: card -10 stays FAILED
        # at the former claim until a scoped re-bench says otherwise.
        self.assertEqual(MANIFEST["bench"]["bench_verdict"], "FAILED")
        self.assertFalse(MANIFEST["bench"]["certified"])
        self.assertEqual(
            MANIFEST["bench"]["scorecard_ref"],
            "test-bench/results/eclipse-legacy-recon-mcp-2026-10-26-10.json")
        self.assertIn("scoped re-bench pending", MANIFEST["status"])


if __name__ == "__main__":
    unittest.main()

# Eclipse Legacy Recon MCP · © 2026 Cyan Eclipse Technologies LLC · cetech.ai
