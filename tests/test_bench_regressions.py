#!/usr/bin/env python3
# Eclipse Legacy Recon MCP
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
# Bench regressions B-LR-1 / B-LR-2 / B-LR-4 (bench run 2026-10-26-2).

"""Regression tests mirroring the bench's failing fixtures:
JS/TS comment/string/template phantoms, the Python triple-quote
string-collateral swallow, and the overlong-path -32603 escape.
Round 3 (bench run 2026-10-26-5): B-LR-8 control-head regex
consequents, B-LR-9 ASI line-leading regex, B-LR-10 keyword-
spelled division unmasking a string tail, B-LR-11 FIFO child.
Round 4 (bench run 2026-10-26-6): B-LR-10 residual — string
precedence inverted/context-free; phantom shape GENERATED
across the full JS operator inventory (see Round4BLR10Matrix)."""
import json
import os
import socket
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))
import recon_engine as eng  # noqa: E402
import server  # noqa: E402


def _tree(files):
    td = tempfile.mkdtemp()
    for rel, content in files.items():
        p = Path(td) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return td


def _observed(td):
    r = eng.scan_target({"path": td})
    return {x["name"] for x in r["dependencies"]["observed"]}


class JsPhantomsBLR1(unittest.TestCase):
    def test_bench_ghost_fixture_exact(self):
        td = _tree({"a.js": (
            "// const x = require('ghostcomment');\n"
            "const s = \"require('ghoststring')\";\n"
            "const t = `import 'ghosttemplate'`;\n"
            "/* require('ghostblock') */\n"
            "const real = require('realpkg');\n")})
        obs = _observed(td)
        self.assertFalse(any(n.startswith("ghost") for n in obs), obs)
        self.assertIn("realpkg", obs)

    def test_real_import_forms_preserved(self):
        lines = [
            "import def from 'mod-a';",
            'import {x} from "mod-b";',
            "import 'mod-c';",
            "export {y} from 'mod-d';",
            'const z = require("mod-e");',
            "import type {T} from 'mod-f';",
        ]
        for lang in ("JavaScript", "TypeScript"):
            names = [m for m, _, _ in eng.scan_imports(lang, lines)]
            self.assertEqual(names, ["mod-a", "mod-b", "mod-c",
                                     "mod-d", "mod-e", "mod-f"], lang)

    def test_multiline_block_and_template_expr_ghosts(self):
        lines = [
            "/* multi",
            "line require('ghost-a')",
            "*/ const w = require('mod-f');",
            "const t = `tpl ${'nested `tick`'} require('ghost-b')`;",
            "const s = 'it\\'s require(\\'ghost-c\\')';"
            " const v = require('mod-g');",
        ]
        names = [m for m, _, _ in eng.scan_imports("JavaScript", lines)]
        self.assertEqual(names, ["mod-f", "mod-g"], names)


class JsRegexLiteralsBLR1Residual(unittest.TestCase):
    """B-LR-1 residual (bench run-4, check X1): JS/TS regex literals
    were not lexed, so import-shaped text inside /.../ minted
    phantom OBSERVED deps, and a regex containing a quote or //
    corrupted masking state and swallowed a same-line real import."""

    def test_x1_ghosts_end_to_end_js_and_ts(self):
        td = _tree({
            "a.js": "const re = /require('ghostr1')/;\n"
                    "const real = require('realpkg');\n",
            "b.ts": "const re = /from 'ghostr2'/;\n"
                    "import realts from 'realtsmod';\n",
            "c.js": "const re = /import 'ghostregex2'/;\n"})
        obs = _observed(td)
        self.assertFalse(any(n.startswith("ghost") for n in obs), obs)
        self.assertIn("realpkg", obs)
        self.assertIn("realtsmod", obs)

    def test_x1_ghosts_scan_imports_both_langs(self):
        lines = [
            "const r1 = /require('ghostr1')/;",
            "const r2 = /from 'ghostr2'/;",
            "const r3 = /import 'ghostregex2'/;",
        ]
        for lang in ("JavaScript", "TypeScript"):
            names = [m for m, _, _ in eng.scan_imports(lang, lines)]
            self.assertEqual(names, [], (lang, names))

    def test_regex_containing_comment_chars_and_same_line_real(self):
        lines = [r"const re = /a\/\/ require('ghostr4')/;"
                 " const z = require('realzz');"]
        for lang in ("JavaScript", "TypeScript"):
            names = [m for m, _, _ in eng.scan_imports(lang, lines)]
            self.assertEqual(names, ["realzz"], (lang, names))

    def test_regex_containing_quote_or_backtick_same_line_real(self):
        lines = [
            "const a = /'/; const x = require('after-quote');",
            "const b = /`tick`/; const y = require('after-tick');",
            r"const c = /don\'t/; const z = require('after-escq');",
        ]
        names = [m for m, _, _ in eng.scan_imports("JavaScript", lines)]
        self.assertEqual(names, ["after-quote", "after-tick",
                                 "after-escq"], names)

    def test_regex_escapes_and_char_classes(self):
        lines = [
            r"const a = /a\/b/; const x = require('after-esc');",
            "const b = /[/]/; const y = require('after-class');",
            "const c = /[a/b]+/gi; const z = require('after-class2');",
            "const d = /x]y/; const w = require('after-bracket');",
        ]
        names = [m for m, _, _ in eng.scan_imports("JavaScript", lines)]
        self.assertEqual(names, ["after-esc", "after-class",
                                 "after-class2", "after-bracket"], names)

    def test_regex_in_operator_contexts_no_phantom(self):
        lines = [
            "function f() { return /require('ghostret')/; }",
            "foo(/import 'ghostarg'/, 1);",
            "const o = {re: /from 'ghostobj'/};",
            "if (x) { y(); } const re = /require('ghostblock')/;",
            "const t = typeof /require('ghosttypeof')/;",
            "const u = !/from 'ghostbang'/.test(s);",
        ]
        for lang in ("JavaScript", "TypeScript"):
            names = [m for m, _, _ in eng.scan_imports(lang, lines)]
            self.assertEqual(names, [], (lang, names))

    def test_division_preserved_same_and_later_lines(self):
        lines = [
            "const q = a / b / c;",
            "x = y / 2; const r = require('real-div');",
            "const q2 = a /",
            "    b / c;",
            "const s = require('real-next-line');",
        ]
        names = [m for m, _, _ in eng.scan_imports("JavaScript", lines)]
        self.assertEqual(names, ["real-div", "real-next-line"], names)

    def test_division_after_value_closers_and_incdec(self):
        lines = [
            "let d1 = (a + b) / c; const r1 = require('div-paren');",
            "let d2 = arr[0] / c; const r2 = require('div-bracket');",
            "let d3 = a++ / b; const r3 = require('div-inc');",
            "let d4 = a-- / b; const r4 = require('div-dec');",
            "let o = {v: 8}; let d5 = o.v / 2;"
            " const r5 = require('div-obj');",
        ]
        names = [m for m, _, _ in eng.scan_imports("JavaScript", lines)]
        self.assertEqual(names, ["div-paren", "div-bracket", "div-inc",
                                 "div-dec", "div-obj"], names)

    def test_unterminated_regex_position_resyncs_next_line(self):
        lines = [
            "const re = /require('ghostunterm')",
            "const r = require('real-after-unterm');",
        ]
        names = [m for m, _, _ in eng.scan_imports("JavaScript", lines)]
        self.assertEqual(names, ["real-after-unterm"], names)

    def test_regex_inside_template_expression(self):
        lines = [
            "const t = `x${/}/.test(s)} require('ghosttpl')`;"
            " const r = require('real-tpl');",
            "const u = `y${/`/.source} import 'ghosttpl2'`;"
            " const s = require('real-tpl2');",
            "const v = `z${a / b / c}`;"
            " const w = require('real-tpl3');",
        ]
        names = [m for m, _, _ in eng.scan_imports("JavaScript", lines)]
        self.assertEqual(names, ["real-tpl", "real-tpl2",
                                 "real-tpl3"], names)


class PythonGuardBLR2(unittest.TestCase):
    def test_bench_realtwo_fixture_exact(self):
        td = _tree({
            "a.py": ('s = "import ghostpystr"\n'
                     '"""\nimport ghostpydoc\n"""\n'
                     "import realpymod\n"
                     'y = "has \\""" tricky"\n'
                     "import realtwo\n"),
            "realpymod.py": "X = 1\n",
            "realtwo.py": "Y = 2\n"})
        obs = _observed(td)
        self.assertFalse(any(n.startswith("ghostpy") for n in obs), obs)
        self.assertIn("realpymod", obs)
        self.assertIn("realtwo", obs)  # was swallowed pre-fix

    def test_triple_delim_inside_ordinary_strings(self):
        lines = [
            "s = 'has \"\"\" inside single quotes'",
            "import beta",
            't = "has \'\'\' inside double quotes"',
            "import gamma",
        ]
        names = [m for m, _, _ in eng.scan_imports("Python", lines)]
        self.assertEqual(names, ["beta", "gamma"], names)

    def test_same_line_open_close_and_comment_delims(self):
        lines = [
            '"""one-line docstring"""',
            "import alpha",
            "# comment containing \"\"\" must not flip the guard",
            "import beta  # trailing \"\"\" comment",
            "import gamma",
        ]
        names = [m for m, _, _ in eng.scan_imports("Python", lines)]
        self.assertEqual(names, ["alpha", "beta", "gamma"], names)

    def test_real_triple_docstring_still_guards(self):
        lines = [
            '"""',
            "import ghost1",
            '"""',
            "import real1",
            "'''",
            "import ghost2",
            "'''",
            "import real2",
        ]
        names = [m for m, _, _ in eng.scan_imports("Python", lines)]
        self.assertEqual(names, ["real1", "real2"], names)


class OverlongPathBLR4(unittest.TestCase):
    def test_engine_overlong_all_entry_points(self):
        for fn in (eng.scan_target, eng.architecture_map,
                   eng.dependency_risk_list, eng.modernization_inputs):
            with self.assertRaises(eng.ToolError) as c:
                fn({"path": "x" * 5000})
            msg = str(c.exception)
            self.assertTrue("TARGET_PATH_INVALID" in msg
                            or "TARGET_NOT_FOUND" in msg, msg)

    def test_engine_overlong_component_variants(self):
        for bad in ("/tmp/" + "x" * 5000, "x" * 300 + "/" + "y" * 5000):
            with self.assertRaises(eng.ToolError) as c:
                eng.scan_target({"path": bad})
            self.assertIn("TARGET_", str(c.exception))

    def test_wire_overlong_no_32603_any_tool(self):
        for tool in server.TOOLS:
            resp = server.handle({
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": tool,
                           "arguments": {"path": "x" * 5000}}})
            self.assertNotEqual(resp.get("error", {}).get("code"),
                                -32603, (tool, resp))
            self.assertTrue(resp["result"]["isError"], (tool, resp))
            payload = json.loads(resp["result"]["content"][0]["text"])
            self.assertIn("TARGET_", payload["error"], (tool, payload))


class Round3BLR8to11(unittest.TestCase):
    """Bench run-5 sub-classes: control-head ')' (B-LR-8), ASI
    after postfix at EOL (B-LR-9), keyword-spelled division whose
    misjudged span closed inside a later string (B-LR-10), and
    non-regular children hanging the walk (B-LR-11)."""

    def test_b_lr8_control_head_regex_consequents(self):
        lines = [
            "if (cond) /require('ghostif')/.test(s);",
            "while (cond) /require('ghostwhile')/.test(s);",
            "for (;;) /require('ghostfor')/.test(s);",
            "with (obj) /require('ghostwith')/.test(s);",
            "try {} catch (e) /require('ghostcatch')/.test(s);",
            "if ((cond)) /require('ghostnested')/.test(s);",
            "const r = require('real-after');",
        ]
        for lang in ("JavaScript", "TypeScript"):
            names = [m for m, _, _ in eng.scan_imports(lang, lines)]
            self.assertEqual(names, ["real-after"], (lang, names))
        td = _tree({"a.js": "\n".join(lines) + "\n"})
        obs = _observed(td)
        self.assertFalse(any(n.startswith("ghost") for n in obs), obs)
        self.assertIn("real-after", obs)

    def test_b_lr8_expression_paren_closes_keep_division(self):
        lines = [
            "let d1 = (a + b) / c; const r1 = require('div-group');",
            "foo(a) / b; const r2 = require('div-call');",
            "const f = (a, b) => a / b;"
            " const r3 = require('div-arrow');",
            "if (x) y / z; const r4 = require('div-ifbody');",
            "arr[i] / b; const r5 = require('div-bracket');",
        ]
        names = [m for m, _, _ in eng.scan_imports("JavaScript", lines)]
        self.assertEqual(names, ["div-group", "div-call", "div-arrow",
                                 "div-ifbody", "div-bracket"], names)

    def test_b_lr8_template_expr_control_head_regex(self):
        lines = [
            "const t = `${(() => { if (ok)"
            " /require('ghosttif')/.test(s); return 0; })()}`;"
            " const r = require('real-tplctrl');",
        ]
        names = [m for m, _, _ in eng.scan_imports("JavaScript", lines)]
        self.assertEqual(names, ["real-tplctrl"], names)

    def test_b_lr9_asi_line_leading_regex_no_phantom(self):
        lines = [
            "x++",
            "/require('ghostasi')/.test(s);",
            "y--",
            "/require('ghostasi2')/.test(s);",
            "let done = compute()",
            "/require('ghostasi3')/.test(s);",
            "const r = require('real-after-asi');",
        ]
        for lang in ("JavaScript", "TypeScript"):
            names = [m for m, _, _ in eng.scan_imports(lang, lines)]
            self.assertEqual(names, ["real-after-asi"], (lang, names))

    def test_b_lr9_trailing_operator_division_preserved(self):
        lines = [
            "const q = a /",
            "    b / c;",
            "const s = require('real-trailing');",
            "const q2 = a / b /",
            "    c; const t = require('real-trailing2');",
        ]
        names = [m for m, _, _ in eng.scan_imports("JavaScript", lines)]
        self.assertEqual(names, ["real-trailing", "real-trailing2"],
                         names)

    def test_b_lr10_keyword_division_string_tail_masked(self):
        lines = [
            'of / b; t="x/ require(\'ghostkw\')"',
            'obj.of / b; t="x/ require(\'ghostkw2\')"',
            'obj.in / b; t="x/ require(\'ghostkwin\')"',
            "const r = require('real-after-kw');",
        ]
        for lang in ("JavaScript", "TypeScript"):
            names = [m for m, _, _ in eng.scan_imports(lang, lines)]
            self.assertEqual(names, ["real-after-kw"], (lang, names))
        td = _tree({"a.js": "\n".join(lines) + "\n"})
        obs = _observed(td)
        self.assertFalse(any(n.startswith("ghostkw") for n in obs), obs)
        self.assertIn("real-after-kw", obs)

    def test_b_lr11_fifo_and_socket_children_skipped_counted(self):
        td = _tree({"a.js": "const r = require('realpkg');\n"})
        os.mkfifo(Path(td) / "pipe.js")
        sock = socket.socket(socket.AF_UNIX)
        sock.bind(str(Path(td) / "sock.js"))
        try:
            t0 = time.time()
            r = eng.scan_target({"path": td})
            elapsed = time.time() - t0
        finally:
            sock.close()
        self.assertLess(elapsed, 5)
        self.assertEqual(r["non_regular_files_skipped"], 2)
        self.assertEqual(r["architecture"]["file_count"], 1)
        self.assertIn("realpkg", _observed(td))

    def test_b_lr11_fifo_only_tree_named_empty_fast(self):
        td = tempfile.mkdtemp()
        os.mkfifo(Path(td) / "only-pipe")
        t0 = time.time()
        with self.assertRaises(eng.ToolError) as c:
            eng.scan_target({"path": td})
        self.assertLess(time.time() - t0, 5)
        self.assertIn("TARGET_EMPTY", str(c.exception))


# B-LR-10 round 4: the full JS binary / assignment / ternary /
# arrow operator inventory from the fix brief. The phantom shape
# (keyword-spelled division slash, then a slash-bearing string
# after an operator) is GENERATED across this inventory — not
# hand-enumerated — so the whole class is pinned, not the 13
# wire-confirmed instances.
_LR10_OPS = ["+", "-", "*", "%", "**", "<<", ">>", ">>>", "<",
             ">", "<=", ">=", "==", "===", "!=", "!==", "&", "|",
             "^", "&&", "||", "??", "=", "+=", "-=", "*=", "%=",
             "**=", "<<=", ">>=", "&=", "|=", "^=", "=>", "?", ":"]


def _lr10_matrix_lines():
    """Yield (label, line) for every generated phantom shape."""
    for op in _LR10_OPS:
        for q, iq in (('"', "'"), ("'", '"')):
            yield (f"op{op}-{q}",
                   f"of / b {op} {q}p/ require({iq}ghostm{iq}){q}")
        yield (f"op{op}-tpl",
               f"of / b {op} `p/ require('ghostm')`")
    # Span-start shapes: string opens the misjudged span
    # (ghostdivstr: space after slash; ghostfirstq: quote as
    # first pattern char).
    yield ("ghostdivstr", "of / \"p/ require('ghostdivstr')\"")
    yield ("ghostfirstq", "of /\"p/ require('ghostfirstq')\"")
    yield ("start-sq", "of /'p/ require(\"ghoststartsq\")'")
    yield ("start-space-sq", "of / 'p/ require(\"ghoststartsq2\")'")


class Round4BLR10Matrix(unittest.TestCase):
    """B-LR-10 residual (bench run-6, X1): string precedence
    inside a putative regex span fired only for a declared
    context set, minting phantoms after arithmetic / comparison
    / shift / arrow operators and at span start. Round 4 inverts
    precedence (quote = string opener unless provably pattern
    content); these generated cases pin the class."""

    def test_generated_operator_matrix_no_phantoms(self):
        real = "const r = require('real-matrix');"
        count = 0
        for label, line in _lr10_matrix_lines():
            count += 1
            for lang in ("JavaScript", "TypeScript"):
                with self.subTest(shape=label, lang=lang):
                    names = [m for m, _, _ in
                             eng.scan_imports(lang, [line, real])]
                    self.assertEqual(names, ["real-matrix"],
                                     (label, lang, names))
        self.assertGreaterEqual(count, 100)  # matrix really ran

    def test_bench13_named_shapes_end_to_end(self):
        shapes = [
            "of / b + \"p/ require('ghostctx_plus')\"",
            "of / b - \"p/ require('ghostctx_minus')\"",
            "of / b * \"p/ require('ghostctx_star')\"",
            "of / b % \"p/ require('ghostctx_pct')\"",
            "of / b ^ \"p/ require('ghostctx_caret')\"",
            "of / b < \"p/ require('ghostctx_lt')\"",
            "of / b > \"p/ require('ghostctx_gt')\"",
            "of / b ** \"p/ require('ghostctx_pow')\"",
            "of / b << \"p/ require('ghostctx_shl')\"",
            "of / b => \"p/ require('ghostctx_arrow')\"",
            "of / \"p/ require('ghostdivstr')\"",
            "of /\"p/ require('ghostfirstq')\"",
            "of / b + 'p/ require(\"ghostsqplus\")'",
        ]
        td = _tree({"a.js": "\n".join(shapes) + "\n"
                            "const r = require('real-bench13');\n"})
        obs = _observed(td)
        self.assertFalse(any(n.startswith("ghost") for n in obs), obs)
        self.assertIn("real-bench13", obs)

    def test_bare_quote_regex_preserved_explicit(self):
        # Brief's explicit case: /'/ is a real regex whose pattern
        # is a bare quote — masking must keep the same span and
        # the same-line real import must survive.
        lines = [
            "const a = /'/; const x = require('after-quote');",
            'const b = /"/; const y = require("after-dquote");',
            "const c = /`tick`/; const z = require('after-tick');",
        ]
        names = [m for m, _, _ in eng.scan_imports("JavaScript", lines)]
        self.assertEqual(names, ["after-quote", "after-dquote",
                                 "after-tick"], names)

    def test_string_follow_continuations_still_masked(self):
        lines = [
            "of / b + \"p/ require('ghostfw1')\" instanceof String",
            "of / b + \"p/ require('ghostfw2')\".length",
            "foo(of / b, \"p/ require('ghostfw3')\")",
            "of / b + \"a/ require('ghostfw4')\""
            " + \"c/ require('ghostfw5')\"",
            "const r = require('real-follow');",
        ]
        names = [m for m, _, _ in eng.scan_imports("JavaScript", lines)]
        self.assertEqual(names, ["real-follow"], names)


# B-LR-13 + B-LR-10 residuals 1/3 round 5 (bench run-7, X1):
# (A) string-follow plausibility word set omitted TS as /
# satisfies (+ the rest of the grammar's follow inventory);
# (B) a quote-pair spanning a slash whose pair close is
# operator-followed made string precedence truncate a genuine
# regex span, exposing its import-shaped pattern tail;
# (C) the balanced-${} gate rejected template operands whose
# TEXT holds a raw '}'.
_LR13_WORD_FOLLOWS = ["in obj", "of items", "instanceof String",
                      "as const", "as unknown as string",
                      "satisfies Record<string, unknown>",
                      "extends string", "assert { type: 'json' }",
                      "with { type: 'json' }"]
_LR13_PUNCT_FOLLOWS = ["", ";", ", y", ")", "]", "}", " ? y : z",
                       ".length", "(y)", " + y", " === y", ": y",
                       " && y", " ?? y"]


def _lr13_matrix_lines():
    """Generated follow-token matrix: every legal follow class
    (word inventory + punctuator/operator/EOL set) x every
    string form (double / single / template)."""
    for follow in _LR13_WORD_FOLLOWS + _LR13_PUNCT_FOLLOWS:
        yield (f"dq-{follow!r}",
               f"of / b + \"p/ require('ghostA')\" {follow}")
        yield (f"sq-{follow!r}",
               f"of / b + 'p/ require(\"ghostA\")' {follow}")
        yield (f"tpl-{follow!r}",
               f"of / b + `p/ require('ghostA')` {follow}")


class Round5BLR13AndResiduals(unittest.TestCase):
    def test_a_generated_follow_token_matrix_no_phantoms(self):
        real = "const r = require('real-matrix5');"
        count = 0
        for label, line in _lr13_matrix_lines():
            count += 1
            for lang in ("JavaScript", "TypeScript"):
                with self.subTest(shape=label, lang=lang):
                    names = [m for m, _, _ in
                             eng.scan_imports(lang, [line, real])]
                    self.assertEqual(names, ["real-matrix5"],
                                     (label, lang, names))
        self.assertGreaterEqual(count, 60)  # matrix really ran

    def test_a_wire_shapes_end_to_end_ts_and_js(self):
        td = _tree({
            "a.ts": "of / b + \"p/ require('wghostA1')\" as const\n"
                    "of / b + \"p/ require('wghostA2')\""
                    " satisfies object\n"
                    "import realts from 'realts5';\n",
            "b.js": "of / b + 'p/ require(\"wghostA1j\")' as const\n"
                    "const r = require('realjs5');\n"})
        obs = _observed(td)
        self.assertFalse(any(n.startswith("wghost") for n in obs), obs)
        self.assertIn("realts5", obs)
        self.assertIn("realjs5", obs)

    def test_b_longest_coherent_span_shapes(self):
        shapes = [
            "const re = /x'b/c' + require('ghostB1')/;",
            "const o = {re: /x'b/c' + require('ghostBobj')/};",
            "const re = /x'b/c' + from 'ghostBimp'/;",
            "function f(){ return /x'b/c'"
            " + require('ghostBret')/; }",
            "foo(/x'b/c' + require('ghostBarg')/);",
            "if (/x'b/c' + require('ghostBcond')/.test(s)) {}",
            "const re = /x'b/c' + 'd/e'"
            " + require('ghostB2p')/;",
            "const re = /[/]x'b/c' + require('ghostBcls')/;",
            "const re = /[']x'b/c' + require('ghostBclsq')/;",
            'const re = /x"b/c" + require("ghostBdq")/;',
        ]
        real = "const r = require('real-b5');"
        for lang in ("JavaScript", "TypeScript"):
            for line in shapes:
                with self.subTest(shape=line, lang=lang):
                    names = [m for m, _, _ in
                             eng.scan_imports(lang, [line, real])]
                    self.assertEqual(names, ["real-b5"],
                                     (line, lang, names))
        td = _tree({"a.js": "\n".join(shapes) + "\n" + real + "\n"})
        obs = _observed(td)
        self.assertFalse(any(n.startswith("ghostB") for n in obs), obs)
        self.assertIn("real-b5", obs)

    def test_b_string_wins_when_regex_reading_incoherent(self):
        # Guard: the coherent-span rule must not resurrect the
        # round-4 phantoms — here the pattern reading closes at
        # the string's internal slash with an illegal follow
        # (or never closes), so string precedence still fires.
        lines = [
            "of / b + \"p/ require('ghostInc1')\" as const",
            "of / \"p/ require('ghostInc2')\"",
            "const a = /'/; const x = require('after-quote5');",
            "const r = require('real-inc5');",
        ]
        names = [m for m, _, _ in eng.scan_imports("JavaScript", lines)]
        self.assertEqual(names, ["after-quote5", "real-inc5"], names)

    def test_c_raw_brace_template_operands(self):
        shapes = [
            "of / b + `x}y/ require('ghostC1')`",
            "of / `x} / require('ghostC2')`;",
            "of / b + `a${x}b}c/ require('ghostC3')`",
            "of / b + `a{b}c/ require('ghostC4')`",
            "of / b + `a${ {k: 1} }z}w/ require('ghostC5')`",
        ]
        real = "const r = require('real-c5');"
        for lang in ("JavaScript", "TypeScript"):
            for line in shapes:
                with self.subTest(shape=line, lang=lang):
                    names = [m for m, _, _ in
                             eng.scan_imports(lang, [line, real])]
                    self.assertEqual(names, ["real-c5"],
                                     (line, lang, names))
        td = _tree({
            "a.js": "\n".join(shapes) + "\n" + real + "\n",
            "b.ts": shapes[0] + "\nimport t from 'realtsc5';\n"})
        obs = _observed(td)
        self.assertFalse(any(n.startswith("ghostC") for n in obs), obs)
        self.assertIn("real-c5", obs)
        self.assertIn("realtsc5", obs)

    def test_c_enclosing_interp_close_still_pattern_content(self):
        # Preservation (round-4 X2 set): inside ${ }, a '}' at
        # depth 0 is the enclosing close, not template text —
        # the /`/ literal must still end at its own slash and
        # the same-line real import after the template survives.
        lines = [
            "const u = `y${/`/.source} import 'ghosttpl2'`;"
            " const s = require('real-tpl2');",
        ]
        names = [m for m, _, _ in eng.scan_imports("JavaScript", lines)]
        self.assertEqual(names, ["real-tpl2"], names)


# B-LR-10 residual-1, NO-CLOSING-SLASH sub-family (bench run-8,
# card -8, X1 — the one gating defect): JS/TS quote-pair patterns
# where the regex reading NEVER terminates (no closing '/').
# The string reading is coherent (operator follow) while the
# regex reading is incoherent, so round-5 string precedence
# fired and exposed the import-shaped pattern tail as code.
# Shapes below are BYTE-FOR-BYTE the run-7/run-8 wire line for
# the from-form, and the card-named siblings (require / object /
# return / single-quote-pair) reconstructed in the exact same
# lineage shape (/"a/b" + x <form>) — NOT the round-5 builder
# test_b shape (which silently added a closing '/', dropped
# the 'x', and changed the pair to 'b/c').
_NC_EXACT = '''/"a/b" + x from 'wghostBimp';'''
_NC_SIBLINGS = [
    '''/"a/b" + x require('wghostBncReq');''',
    '''const o = {re: /"a/b" + x require('wghostBncObj')};''',
    '''function f(){ return /"a/b" + x require('wghostBncRet'); }''',
    """/'a/b' + x from "wghostBncSq";""",
    '''/`a/b` + x from 'wghostBncTpl';''',
]
_NC_DYN_CLEAN = '''/"a/b" + x import('wghostBncDyn');'''


class Round6BLR10NoClosingSlash(unittest.TestCase):
    def test_exact_run7_line_byte_for_byte_no_phantom(self):
        real = "const r = require('real-nc');"
        for lang in ("JavaScript", "TypeScript"):
            with self.subTest(lang=lang):
                names = [m for m, _, _ in
                         eng.scan_imports(lang, [_NC_EXACT, real])]
                self.assertEqual(names, ["real-nc"], (lang, names))

    def test_no_close_siblings_scan_level_no_phantoms(self):
        real = "const r = require('real-nc');"
        for lang in ("JavaScript", "TypeScript"):
            for line in _NC_SIBLINGS:
                with self.subTest(shape=line, lang=lang):
                    names = [m for m, _, _ in
                             eng.scan_imports(lang, [line, real])]
                    self.assertEqual(names, ["real-nc"],
                                     (line, lang, names))

    def test_no_close_family_end_to_end_real_alongside_caught(self):
        td = _tree({
            "a.js": "\n".join([_NC_EXACT] + _NC_SIBLINGS
                              + [_NC_DYN_CLEAN]) + "\n"
                    "const r = require('real-nc-wire');\n",
            "b.ts": _NC_EXACT + "\n"
                    "import realts from 'realts-nc';\n"})
        obs = _observed(td)
        self.assertFalse(any(n.startswith("wghost") for n in obs), obs)
        self.assertIn("real-nc-wire", obs)
        self.assertIn("realts-nc", obs)

    def test_dyn_form_remains_clean_control(self):
        names = [m for m, _, _ in
                 eng.scan_imports("JavaScript", [_NC_DYN_CLEAN])]
        self.assertEqual(names, [], names)


if __name__ == "__main__":
    unittest.main()

# Eclipse Legacy Recon MCP · © 2026 Cyan Eclipse Technologies LLC · cetech.ai
