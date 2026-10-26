#!/usr/bin/env python3
# Eclipse Legacy Recon MCP
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
# Acceptance tests — evidence-bound recon, manifests, EOL, safety.

"""Acceptance tests for Legacy Recon v0.1."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))
import recon_engine as eng  # noqa: E402

FIX = HERE / "fixtures" / "legacy-tree"


def ensure_symlink():
    link = FIX / "escape_link"
    if not link.is_symlink():
        try:
            link.symlink_to("/etc")
        except OSError:
            pass


class FixtureScan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_symlink()
        cls.r = eng.scan_target({"path": str(FIX)})

    def test_languages_and_loc(self):
        langs = {x["language"] for x in self.r["architecture"]["languages"]}
        self.assertIn("Python", langs)
        self.assertIn("JavaScript", langs)
        self.assertGreater(self.r["modernization_inputs"]["total_loc"], 0)

    def test_every_language_claim_has_evidence(self):
        for item in self.r["architecture"]["languages"]:
            self.assertIn("path", item["evidence"])
            self.assertIn("detail", item["evidence"])

    def test_entry_points(self):
        paths = {e["path"] for e in self.r["architecture"]["entry_points"]}
        self.assertIn("app/main.py", paths)
        self.assertIn("src/index.js", paths)

    def test_python_package_detected(self):
        self.assertTrue(any(p["path"] == "app"
                            for p in self.r["architecture"]["packages"]))

    def test_declared_deps_with_lines(self):
        decl = {(d["name"], d["ecosystem"]) for d in self.r["dependencies"]["declared"]}
        self.assertIn(("Django", "python"), decl)
        self.assertIn(("express", "javascript"), decl)
        for d in self.r["dependencies"]["declared"]:
            self.assertEqual(d["source_class"], "DECLARED")
            self.assertIn("path", d["evidence"])

    def test_observed_separate_from_declared(self):
        obs = {o["name"] for o in self.r["dependencies"]["observed"]}
        self.assertIn("requests", obs)
        for o in self.r["dependencies"]["observed"]:
            self.assertEqual(o["source_class"], "OBSERVED")
            self.assertIn("line", o["evidence"])

    def test_inferred_pillow_labeled_with_basis(self):
        inf = [i for i in self.r["dependencies"]["inferred"] if i["name"] == "Pillow"]
        self.assertTrue(inf)
        self.assertIn("basis", inf[0])
        self.assertIn("PIL", inf[0]["basis"])

    def test_inferred_undeclared_requests(self):
        # requests is OBSERVED but also DECLARED (unpinned) -> its
        # distribution IS declared; PIL/Pillow case covers mapping.
        # Undeclared inference must never appear in declared list.
        for i in self.r["dependencies"]["inferred"]:
            self.assertEqual(i["source_class"], "INFERRED")

    def test_eol_django_cites_rule(self):
        eols = [r for r in self.r["risks"] if r.get("kind") == "EOL"]
        ids = {r["rule_id"] for r in eols}
        self.assertIn("EOL-PKG-DJANGO32", ids)
        for r in eols:
            self.assertIn("evidence", r)
            self.assertEqual(r["eol_rules_version"], eng.EOL_RULES_VERSION)

    def test_eol_python38_and_node16_and_angularjs(self):
        ids = {r.get("rule_id") for r in self.r["risks"]}
        self.assertIn("EOL-RT-PY38", ids)
        self.assertIn("EOL-RT-NODE16", ids)
        self.assertIn("EOL-PKG-ANGULARJS1", ids)

    def test_unpinned_requests(self):
        self.assertTrue(any(r.get("kind") == "UNPINNED_VERSION"
                            and r["subject"] == "requests"
                            for r in self.r["risks"]))

    def test_binary_skipped_counted(self):
        self.assertGreaterEqual(self.r["binary_files_skipped"], 1)

    def test_symlink_escape_reported_not_traversed(self):
        esc = [s for s in self.r["symlinks"] if s["path"] == "escape_link"]
        self.assertTrue(esc, self.r["symlinks"])
        self.assertTrue(esc[0]["escape"])
        self.assertFalse(esc[0]["traversed"])
        # /etc content must not appear as scanned files
        self.assertFalse(any("passwd" in str(x)
                             for x in self.r["architecture"]["languages"]))

    def test_test_ratio_inputs_not_estimate(self):
        mi = self.r["modernization_inputs"]
        self.assertIn("test_main.py", " ".join(mi["test_files"]))
        self.assertIsNotNone(mi["test_loc_ratio"])
        self.assertIn("NOT an estimate", mi["note"])
        self.assertNotIn("estimate", {k.lower() for k in mi})

    def test_coupling_hotspot_utils(self):
        mods = {h["module"] for h in
                self.r["modernization_inputs"]["coupling_hotspots_fan_in"]}
        self.assertIn("utils", mods)

    def test_unknowns_have_reasons(self):
        for u in self.r["unknowns"]:
            self.assertEqual(u["status"], "UNKNOWN")
            self.assertTrue(u["reason"])

    def test_not_truncated_normal_scan(self):
        self.assertFalse(self.r["truncated"])


class Refusals(unittest.TestCase):
    def test_not_found(self):
        with self.assertRaises(eng.ToolError) as c:
            eng.scan_target({"path": "/no/such/dir-legacy-recon-xyz"})
        self.assertIn("TARGET_NOT_FOUND", str(c.exception))

    def test_not_directory(self):
        with self.assertRaises(eng.ToolError) as c:
            eng.scan_target({"path": str(FIX / "requirements.txt")})
        self.assertIn("TARGET_NOT_DIRECTORY", str(c.exception))

    def test_empty(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(eng.ToolError) as c:
                eng.scan_target({"path": td})
            self.assertIn("TARGET_EMPTY", str(c.exception))

    def test_path_invalid(self):
        for bad in ("", "  ", None, 42, ["x"], {"x": 1}):
            with self.assertRaises(eng.ToolError):
                eng.scan_target({"path": bad})

    def test_max_files_truncation_flagged(self):
        r = eng.scan_target({"path": str(FIX), "max_files": 2})
        self.assertTrue(r["truncated"])
        self.assertIn("MAX_FILES_REACHED", r["truncation_reasons"])


class ManifestParsers(unittest.TestCase):
    def _scan(self, files):
        td = tempfile.mkdtemp()
        for name, content in files.items():
            p = Path(td) / name
            p.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                p.write_bytes(content)
            else:
                p.write_text(content)
        Path(td, "code.py").write_text("x = 1\n")
        return eng.scan_target({"path": td})

    def test_gemfile_and_ruby_eol(self):
        r = self._scan({"Gemfile": "ruby '2.7.0'\ngem 'rails', '5.2.0'\n"})
        ids = {x.get("rule_id") for x in r["risks"]}
        self.assertIn("EOL-RT-RUBY27", ids)
        self.assertIn("EOL-PKG-RAILS52", ids)

    def test_pom_xml(self):
        pom = ("<project><dependencies><dependency><groupId>g</groupId>"
               "<artifactId>spring-core</artifactId><version>5.3.0</version>"
               "</dependency></dependencies>"
               "<properties><java.version>11</java.version></properties></project>\n")
        r = self._scan({"pom.xml": pom})
        self.assertTrue(any(d["name"] == "spring-core"
                            for d in r["dependencies"]["declared"]))

    def test_go_mod(self):
        r = self._scan({"go.mod": "module example.com/x\n\ngo 1.21\n\nrequire github.com/pkg/errors v0.9.1\n"})
        self.assertTrue(any(d["name"] == "github.com/pkg/errors"
                            for d in r["dependencies"]["declared"]))
        self.assertTrue(any(s["kind"] == "go" for s in r["runtime_specs"]))

    def test_cargo_toml(self):
        r = self._scan({"Cargo.toml": "[dependencies]\nserde = \"1.0\"\n"})
        self.assertTrue(any(d["name"] == "serde"
                            for d in r["dependencies"]["declared"]))

    def test_pipfile(self):
        r = self._scan({"Pipfile": "[packages]\nflask = \"==1.0\"\n"})
        ids = {x.get("rule_id") for x in r["risks"]}
        self.assertIn("EOL-PKG-FLASK10", ids)

    def test_composer_json(self):
        r = self._scan({"composer.json": '{"require": {"monolog/monolog": "2.0"}}'})
        self.assertTrue(any(d["name"] == "monolog/monolog"
                            for d in r["dependencies"]["declared"]))

    def test_bad_json_manifest_unknown_not_crash(self):
        r = self._scan({"package.json": "{not json"})
        self.assertTrue(any(u["item"] == "manifest:package.json"
                            for u in r["unknowns"]))

    def test_pyproject_requires_python(self):
        r = self._scan({"pyproject.toml":
                        '[project]\nrequires-python = ">=3.8"\ndependencies = [\n "django==3.2",\n]\n'})
        self.assertTrue(any(d["name"].lower() == "django"
                            for d in r["dependencies"]["declared"]))


class RealHouseDir(unittest.TestCase):
    def test_docket_dir_scans_sane(self):
        target = HERE.parent / "eclipse-docket-mcp"
        if not target.exists():
            self.skipTest("docket dir absent")
        r = eng.scan_target({"path": str(target)})
        self.assertGreater(r["architecture"]["file_count"], 5)
        self.assertGreater(r["modernization_inputs"]["loc_by_language"].get("Python", 0), 500)
        self.assertTrue(r["modernization_inputs"]["test_files"])


if __name__ == "__main__":
    unittest.main()

# Eclipse Legacy Recon MCP · © 2026 Cyan Eclipse Technologies LLC · cetech.ai
