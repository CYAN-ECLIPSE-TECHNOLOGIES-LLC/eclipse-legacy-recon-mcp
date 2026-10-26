#!/usr/bin/env python3
# Eclipse Legacy Recon MCP
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
# Legacy Recon engine — read-only, evidence-bound static analysis; never executes target code.

"""Eclipse Legacy Recon engine — v0.1.0.

Read-only static analysis of a caller-supplied local directory.
Never executes, imports, or shells out to target code; no network.

Novel mechanism — evidence-bound recon: every claim cites a file
path plus the manifest line or structural fact it rests on;
anything not determinable statically is UNKNOWN with a reason
(never a guessed stack); the dependency inventory keeps DECLARED
(manifest), OBSERVED (import statements) and INFERRED (labeled
inference with basis) in separate lists, never blended.
"""
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

DESCRIPTOR = ("Read-only legacy codebase recon — architecture map, "
              "dependency/EOL risk list, modernization-estimate "
              "inputs. Every claim cites its evidence; unknowns "
              "are reported as UNKNOWN, never guessed.")

EOL_RULES_VERSION = "2026-10-25.1"
MAX_FILES_DEFAULT = 5000
MAX_FILES_HARD = 50000
MAX_TEXT_BYTES = 1_000_000
SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules",
             ".venv", "venv", "vendor", ".tox", "dist", "build",
             ".mypy_cache", ".pytest_cache"}


class ToolError(Exception):
    """Named, fail-closed refusal."""


# ------------------------------------------------------------ guard
_INT_SHAPED_RE = re.compile(r"^[+-]?\d+$")


def coerce_int_param(value, name, refusal):
    """House reference guard (Blackbox pattern): accepts real int,
    int-shaped string, integral float; refuses bool / other types
    BY NAME, never a bare int() escape."""
    if isinstance(value, bool):
        raise ToolError(f"{refusal}: {name} must be an integer, not a boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and _INT_SHAPED_RE.match(value.strip()):
        return int(value.strip())
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raise ToolError(
        f"{refusal}: {name} must be an integer (got "
        f"{type(value).__name__})")


# ------------------------------------------------------------ EOL rules
# Explicit, versioned-in-code rules table. A version matches a rule
# only on an exact major[.minor] prefix pin. No rule match = no EOL
# claim is made (absence of a rule is NOT a claim of support).
# Fields: rule_id, subject_kind (runtime|package), ecosystem,
# name (lowercase), version_prefix, eol_date, detail.
EOL_RULES = [
    ("EOL-RT-PY27", "runtime", "python", "python", "2.7", "2020-01-01", "Python 2.7 reached end-of-life 2020-01-01."),
    ("EOL-RT-PY36", "runtime", "python", "python", "3.6", "2021-12-23", "Python 3.6 reached end-of-life 2021-12-23."),
    ("EOL-RT-PY37", "runtime", "python", "python", "3.7", "2023-06-27", "Python 3.7 reached end-of-life 2023-06-27."),
    ("EOL-RT-PY38", "runtime", "python", "python", "3.8", "2024-10-07", "Python 3.8 reached end-of-life 2024-10-07."),
    ("EOL-RT-NODE12", "runtime", "node", "node", "12", "2022-04-30", "Node.js 12 reached end-of-life 2022-04-30."),
    ("EOL-RT-NODE14", "runtime", "node", "node", "14", "2023-04-30", "Node.js 14 reached end-of-life 2023-04-30."),
    ("EOL-RT-NODE16", "runtime", "node", "node", "16", "2023-09-11", "Node.js 16 reached end-of-life 2023-09-11."),
    ("EOL-RT-NODE18", "runtime", "node", "node", "18", "2025-04-30", "Node.js 18 reached end-of-life 2025-04-30."),
    ("EOL-RT-PHP74", "runtime", "php", "php", "7.4", "2022-11-28", "PHP 7.4 reached end of security support 2022-11-28."),
    ("EOL-RT-PHP80", "runtime", "php", "php", "8.0", "2023-11-26", "PHP 8.0 reached end of security support 2023-11-26."),
    ("EOL-RT-RUBY27", "runtime", "ruby", "ruby", "2.7", "2023-03-31", "Ruby 2.7 reached end-of-life 2023-03-31."),
    ("EOL-RT-RUBY30", "runtime", "ruby", "ruby", "3.0", "2024-03-31", "Ruby 3.0 reached end-of-life 2024-03-31."),
    ("EOL-PKG-DJANGO22", "package", "python", "django", "2.2", "2022-04-01", "Django 2.2 LTS reached end of extended support 2022-04-01."),
    ("EOL-PKG-DJANGO32", "package", "python", "django", "3.2", "2024-04-01", "Django 3.2 LTS reached end of extended support 2024-04-01."),
    ("EOL-PKG-DJANGO40", "package", "python", "django", "4.0", "2023-08-01", "Django 4.0 reached end of mainstream support 2023-08-01."),
    ("EOL-PKG-DJANGO41", "package", "python", "django", "4.1", "2024-04-01", "Django 4.1 reached end of mainstream support 2024-04-01."),
    ("EOL-PKG-ANGULARJS1", "package", "javascript", "angular", "1.", "2021-12-31", "AngularJS 1.x reached end-of-life 2021-12-31."),
    ("EOL-PKG-RAILS52", "package", "ruby", "rails", "5.2", "2022-06-01", "Rails 5.2 reached end-of-life 2022-06-01."),
    ("EOL-PKG-RAILS60", "package", "ruby", "rails", "6.0", "2024-10-01", "Rails 6.0 reached end-of-life 2024-10-01."),
    ("EOL-PKG-FLASK10", "package", "python", "flask", "1.0", "2021-05-01", "Flask 1.0 line superseded; 1.x received no fixes after 2021-05."),
]


def _version_prefix_match(version, prefix):
    if not version:
        return False
    v = version.strip().lstrip("v=<>~^* ").strip()
    if prefix.endswith("."):
        return v.startswith(prefix)
    return v == prefix or v.startswith(prefix + ".")


def eol_check(kind, ecosystem, name, version, evidence):
    """Return an EOL risk dict citing rule_id, or None."""
    for rid, k, eco, n, prefix, date, detail in EOL_RULES:
        if k == kind and eco == ecosystem and n == name.lower() \
                and _version_prefix_match(version or "", prefix):
            return {"kind": "EOL", "rule_id": rid, "subject": name,
                    "version": version, "eol_date": date,
                    "detail": detail, "evidence": evidence,
                    "eol_rules_version": EOL_RULES_VERSION}
    return None


# ------------------------------------------------------------ languages
EXT_LANG = {
    ".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript",
    ".cjs": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".jsx": "JavaScript", ".java": "Java", ".go": "Go",
    ".rb": "Ruby", ".php": "PHP", ".rs": "Rust", ".c": "C",
    ".h": "C", ".cpp": "C++", ".cc": "C++", ".cs": "C#",
    ".sh": "Shell", ".bash": "Shell", ".html": "HTML",
    ".css": "CSS", ".sql": "SQL", ".swift": "Swift",
    ".kt": "Kotlin", ".scala": "Scala", ".pl": "Perl",
    ".lua": "Lua", ".ex": "Elixir", ".erl": "Erlang",
}
MANIFEST_NAMES = {
    "requirements.txt": "python", "Pipfile": "python",
    "pyproject.toml": "python", "setup.py": "python",
    "setup.cfg": "python", "package.json": "javascript",
    "Gemfile": "ruby", "pom.xml": "java", "build.gradle": "java",
    "go.mod": "go", "Cargo.toml": "rust", "composer.json": "php",
}
ENTRY_NAMES = {"main.py", "__main__.py", "server.py", "app.py",
               "manage.py", "wsgi.py", "index.js", "main.js",
               "server.js", "app.js", "main.go", "main.rs",
               "Program.cs", "index.php", "main.rb"}
LAYER_DIRS = {"api": "api/interface", "controllers": "api/interface",
              "routes": "api/interface", "services": "service",
              "service": "service", "models": "model/data",
              "model": "model/data", "db": "model/data",
              "database": "model/data", "utils": "utility",
              "util": "utility", "helpers": "utility",
              "lib": "library", "core": "core", "config": "config",
              "tests": "test", "test": "test", "spec": "test",
              "views": "presentation", "templates": "presentation",
              "static": "presentation", "cmd": "entry/cmd",
              "bin": "entry/cmd"}
# Import-root -> distribution name (basis for INFERRED entries).
DIST_MAP = {"PIL": "Pillow", "yaml": "PyYAML", "cv2": "opencv-python",
            "sklearn": "scikit-learn", "bs4": "beautifulsoup4",
            "dotenv": "python-dotenv", "jwt": "PyJWT",
            "Crypto": "pycryptodome", "serial": "pyserial",
            "usb": "pyusb", "gi": "PyGObject"}
PY_STDLIB = set(getattr(__import__("sys"), "stdlib_module_names", set()))
JS_BUILTINS = {"fs", "path", "http", "https", "os", "util", "events",
               "crypto", "url", "stream", "buffer", "process"}


def _ev(path, detail, line=None):
    ev = {"path": path, "detail": detail}
    if line is not None:
        ev["line"] = line
    return ev


def _is_test(rel):
    p = rel.lower()
    name = Path(p).name
    return ("/tests/" in "/" + p or p.startswith("tests/")
            or name.startswith("test_") or name.endswith("_test.py")
            or name.endswith("_test.go") or ".test." in name
            or ".spec." in name or name.endswith("_spec.rb"))


# ------------------------------------------------------------ manifests
def _lines(path_abs):
    try:
        return path_abs.read_text(encoding="utf-8", errors="strict").splitlines()
    except (UnicodeDecodeError, OSError):
        return None


def parse_manifest(rel, abs_path, declared, runtime_specs, unknowns):
    """Parse one manifest; append DECLARED entries w/ line evidence."""
    name = Path(rel).name
    eco = MANIFEST_NAMES.get(name)
    if eco is None:
        return
    lines = _lines(abs_path)
    if lines is None:
        unknowns.append({"item": f"manifest:{rel}", "status": "UNKNOWN",
                         "reason": "manifest is not valid UTF-8 text; not parsed"})
        return

    def add(pkg, version, lineno, raw):
        declared.append({
            "name": pkg, "version": version, "ecosystem": eco,
            "source_class": "DECLARED",
            "evidence": _ev(rel, f"manifest line: {raw.strip()[:160]}", lineno)})

    if name == "requirements.txt":
        for i, raw in enumerate(lines, 1):
            s = raw.strip()
            if not s or s.startswith("#") or s.startswith("-"):
                continue
            m = re.match(r"^([A-Za-z0-9_.\-]+)\s*(.*)$", s)
            if m:
                spec = m.group(2).strip() or None
                ver = spec.lstrip("=").strip() if spec and spec.startswith("==") else spec
                add(m.group(1), ver, i, raw)
    elif name == "Pipfile":
        in_pkg = False
        for i, raw in enumerate(lines, 1):
            s = raw.strip()
            if s.startswith("["):
                in_pkg = s in ("[packages]", "[dev-packages]")
                continue
            if in_pkg:
                m = re.match(r'^([A-Za-z0-9_.\-]+)\s*=\s*"([^"]*)"', s)
                if m:
                    add(m.group(1), None if m.group(2) == "*" else m.group(2), i, raw)
    elif name in ("package.json", "composer.json"):
        try:
            data = json.loads("\n".join(lines))
        except ValueError:
            unknowns.append({"item": f"manifest:{rel}", "status": "UNKNOWN",
                             "reason": "JSON manifest failed to parse; dependencies not determinable statically from it"})
            return
        sections = ("dependencies", "devDependencies") if name == "package.json" else ("require", "require-dev")
        for sec in sections:
            deps = data.get(sec)
            if isinstance(deps, dict):
                for pkg, ver in deps.items():
                    ln = next((i for i, l in enumerate(lines, 1)
                               if f'"{pkg}"' in l), None)
                    add(pkg, str(ver), ln, lines[ln - 1] if ln else pkg)
        if name == "package.json":
            eng = data.get("engines")
            if isinstance(eng, dict) and isinstance(eng.get("node"), str):
                ln = next((i for i, l in enumerate(lines, 1) if '"node"' in l), None)
                runtime_specs.append(("node", "node", eng["node"],
                                       _ev(rel, f"engines.node: {eng['node']}", ln)))
            main = data.get("main")
            if isinstance(main, str):
                runtime_specs.append(("javascript-main", main, None,
                                      _ev(rel, f"package.json main: {main}")))
    elif name == "Gemfile":
        for i, raw in enumerate(lines, 1):
            m = re.match(r"""^\s*gem\s+['"]([^'"]+)['"](?:\s*,\s*['"]([^'"]+)['"])?""", raw)
            if m:
                add(m.group(1), m.group(2), i, raw)
            m2 = re.match(r"^\s*ruby\s+['\"]([^'\"]+)['\"]", raw)
            if m2:
                runtime_specs.append(("ruby", "ruby", m2.group(1),
                                      _ev(rel, f"Gemfile ruby directive: {m2.group(1)}", i)))
    elif name == "pom.xml":
        # Pair <artifactId>/<version> inside each <dependency> block.
        text = "\n".join(lines)
        for block in re.finditer(r"<dependency>(.*?)</dependency>", text, re.S):
            body, start = block.group(1), block.start(1)
            a = re.search(r"<artifactId>([^<]+)</artifactId>", body)
            v = re.search(r"<version>([^<]+)</version>", body)
            if a:
                ln = text[:start + a.start()].count("\n") + 1
                add(a.group(1), v.group(1) if v else None, ln,
                    lines[ln - 1] if ln <= len(lines) else a.group(1))
        jv = re.search(r"<(?:java\.version|maven\.compiler\.source)>([^<]+)</", text)
        if jv:
            ln = text[:jv.start()].count("\n") + 1
            runtime_specs.append(("java", "java", jv.group(1),
                                  _ev(rel, f"pom.xml java version: {jv.group(1)}", ln)))
    elif name == "go.mod":
        in_req = False
        for i, raw in enumerate(lines, 1):
            s = raw.strip()
            m = re.match(r"^module\s+(\S+)", s)
            if m:
                runtime_specs.append(("go-module", m.group(1), None,
                                      _ev(rel, f"go.mod module: {m.group(1)}", i)))
            m = re.match(r"^go\s+(\d+\.\d+)", s)
            if m:
                runtime_specs.append(("go", "go", m.group(1),
                                      _ev(rel, f"go.mod go directive: {m.group(1)}", i)))
            if s.startswith("require ("):
                in_req = True
                continue
            if in_req and s == ")":
                in_req = False
                continue
            m = re.match(r"^require\s+(\S+)\s+(v?\S+)", s)
            if m:
                add(m.group(1), m.group(2), i, raw)
            elif in_req:
                m = re.match(r"^(\S+)\s+(v?\S+)", s)
                if m:
                    add(m.group(1), m.group(2), i, raw)
    elif name == "Cargo.toml":
        in_dep = False
        for i, raw in enumerate(lines, 1):
            s = raw.strip()
            if s.startswith("["):
                in_dep = s == "[dependencies]"
                continue
            if in_dep:
                m = re.match(r'^([A-Za-z0-9_\-]+)\s*=\s*"([^"]*)"', s)
                if m:
                    add(m.group(1), m.group(2), i, raw)
    elif name == "pyproject.toml":
        for i, raw in enumerate(lines, 1):
            m = re.match(r'^\s*"([A-Za-z0-9_.\-]+)(?:\s*(==|>=|<=|~=|>|<)\s*([^"]*))?"\s*,?\s*$', raw)
            if m and ("dependencies" in "\n".join(lines[max(0, i - 30):i]).lower()):
                add(m.group(1), m.group(3) if m.group(2) == "==" else
                    ((m.group(2) or "") + (m.group(3) or "") or None), i, raw)
            m2 = re.search(r'requires-python\s*=\s*"([^"]+)"', raw)
            if m2:
                runtime_specs.append(("python", "python", m2.group(1),
                                      _ev(rel, f"requires-python: {m2.group(1)}", i)))
    elif name in ("setup.py", "setup.cfg"):
        for i, raw in enumerate(lines, 1):
            m = re.search(r"python_requires\s*=\s*['\"]([^'\"]+)['\"]", raw)
            if m:
                runtime_specs.append(("python", "python", m.group(1),
                                      _ev(rel, f"python_requires: {m.group(1)}", i)))


# ------------------------------------------------------------ imports
IMPORT_RES = [
    ("Python", re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)")),
    ("JavaScript", re.compile(r"""(?:require\(|from\s+|import\s+)\s*['"]([^'./][^'"]*)['"]""")),
    ("TypeScript", re.compile(r"""(?:require\(|from\s+|import\s+)\s*['"]([^'./][^'"]*)['"]""")),
    ("Go", re.compile(r'^\s*(?:import\s+)?"([a-z0-9.\-_/]+)"')),
    ("Ruby", re.compile(r"""^\s*require\s+['"]([^'"]+)['"]""")),
    ("Java", re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+);")),
    ("PHP", re.compile(r"^\s*use\s+([\w\\]+);")),
]


# ------------------------------------------ comment/string masking
# B-LR-1/B-LR-2: import extraction runs on MASKED text — comments,
# string literals and (JS) template literals are blanked by small
# lexer passes before the import regexes run, so prose can never
# mint an OBSERVED dep, and delimiters inside ordinary strings can
# never flip the prose guard and swallow a real import.
# Residual limits (documented): raw strings (Python r"...") treat
# backslash as a literal, so an escaped-looking quote inside one
# can end the mask early. JS regex literals ARE lexed (B-LR-1
# residual fix): a '/' in a regex-permitting token context is
# scanned as a literal (escapes + [...] classes honoured) and
# blanked like a string. Regex-vs-division is decided by the
# standard token-context heuristic; a '}' closing an object
# literal counts as a value, one closing a block as a statement
# boundary (brace-kind is tracked). Where the heuristic cannot
# decide, the phantom-safe reading wins: a regex-position '/'
# with no closing slash on the line is masked to end-of-line
# (resync at the newline), so non-code text never mints a dep,
# at the price of possibly masking a misjudged division tail.
# Where a single-line string is unterminated, the masker resyncs
# at the newline — ambiguity resolves toward EMITTING code on
# later lines, never toward swallowing it.
# Round 3 (B-LR-8/9/10): (8) a paren stack records whether each
# '(' opened a control-flow head (immediately after if / while /
# for / with / catch / switch); a ')' closing such a head leaves
# the lexer at expression-start, so an unbraced regex consequent
# is a regex, while ')' closing a call / grouping / arrow-param
# list stays a value (division preserved). (9) ASI rule: a
# newline after a value / postfix ++/-- token resets the lexer
# to expression-start, so a line-leading '/' opens a regex (a
# division slash belongs at the END of the previous line, e.g.
# 'a /\n b' — operator-leading division continuations across a
# newline are the documented sacrifice, phantom-safe). (10)
# string precedence inside _js_regex_end: a quote in code
# position (after = ( , : ; [ { & | ! ?) whose quoted segment
# itself contains a '/' truncates the putative regex span at
# the string's closing quote — a misjudged regex/division call
# can never unmask a string tail as code.
# Round 4 (B-LR-10 residual): the declared-context set kept
# minting phantoms after every operator outside it (+ - * % ^
# < > ** << =>, span start, first pattern char) — precedence is
# now INVERTED and context-free: any quote (or template
# literal) met while scanning a
# putative regex span is presumed a code string opener unless
# it is provably pattern content — escaped, inside a [...]
# class, unpaired on the line, or failing the plausibility
# check (a real string's close is followed by an operator /
# punctuator / end-of-line / word operator; a pattern quote
# whose close-scan lands on a later string's OPENING quote is
# followed by that string's content, an identifier char, and
# fails). A plausible quote whose segment contains a '/'
# truncates the span at the string's closing quote, in ANY
# operator / expression context or at span start.
# Round 5 (FINAL; bench run-7 X1): (A, B-LR-13) the follow-word
# inventory is completed from the grammar — _JS_STRING_FOLLOW_
# WORDS now also carries TS as / satisfies / extends and
# import-attribute assert / with. (B, B-LR-10 residual 1)
# LONGEST-COHERENT-SPAN: string precedence fires only when
# the quote-as-pattern reading fails to close coherently —
# if treating the quote as pattern content lets the span close
# past the pair (closing '/' + flags + a legal regex-follow
# token, see _js_regex_coherent_end), the regex reading wins
# and the whole span is masked, so an operator-followed pair
# close can no longer expose a pattern tail as code. When
# neither reading is coherent the phantom-safe law is
# unchanged (mask MORE, to EOL, never less). (C, B-LR-10
# residual 3) the template balance gate counts only ${-opened
# braces — a raw '}' in template text unbalances nothing.


def _blank(out, text, start, end):
    for k in range(start, min(end, len(text))):
        out[k] = "\n" if text[k] == "\n" else " "


def _mask_python(text):
    """Blank comments and string/triple-string literals (code kept).

    Triple delimiters are only honoured from code positions: a
    delimiter sequence inside a '...' / "..." literal or a #
    comment is inert, and same-line open+close pairs balance out.
    """
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "#":
            j = text.find("\n", i)
            j = n if j < 0 else j
            _blank(out, text, i, j)
            i = j
            continue
        delim = None
        if text.startswith('"""', i):
            delim = '"""'
        elif text.startswith("'''", i):
            delim = "'''"
        if delim:
            j = i + 3
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text.startswith(delim, j):
                    j += 3
                    break
                j += 1
            _blank(out, text, i, j)
            i = min(j, n)
            continue
        if c in "'\"":
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == c:
                    j += 1
                    break
                if text[j] == "\n":
                    break  # unterminated: resync, never swallow
                j += 1
            _blank(out, text, i, j)
            i = min(j, n)
            continue
        i += 1
    return "".join(out)


def _find_js_string_end(text, i):
    quote = text[i]
    j, n = i + 1, len(text)
    while j < n:
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == quote:
            return j + 1
        if text[j] == "\n":
            return j
        j += 1
    return n


# -------------------------------------------- JS regex literals
# Token-context heuristic (prev significant token -> (kind, text)):
# kind 'value' / 'incdec'  -> '/' is division, NOT a regex start
#   (identifier, number, string/template/regex literal, ')', ']',
#    '}' closing an object literal, '++', '--');
# kind 'start' / 'op' / 'kw' / 'block_end' -> '/' begins a regex
#   (operator or punctuator, expression keyword, start of input,
#    '}' closing a block). Brace kind is tracked so '}' can be
#   told apart. Phantom-safe tie-break: see module notes above.
_JS_VALUE_WORDS = {"this", "true", "false", "null", "undefined",
                   "super"}
_JS_REGEX_WORDS = {"return", "typeof", "case", "delete", "void",
                   "in", "of", "instanceof", "new", "throw", "yield",
                   "await", "else", "do", "try", "finally"}
_JS_IDENT_RE = re.compile(r"[A-Za-z_$][\w$]*")
_JS_NUMBER_RE = re.compile(
    r"(?:0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+"
    r"|\d[\d_]*(?:\.[\d_]*)?(?:[eE][+-]?\d+)?"
    r"|\.\d+(?:[eE][+-]?\d+)?)n?")
_JS_MULTI_OPS = (">>>=",
                 "===", "!==", ">>>", "<<=", ">>=", "**=", "&&=",
                 "||=", "??=", "...",
                 "=>", "==", "!=", "<=", ">=", "&&", "||", "??",
                 "?.", "**", "<<", ">>", "+=", "-=", "*=", "/=",
                 "%=", "&=", "|=", "^=", "++", "--")
_JS_SINGLE_OPS = set("()[],;:?~!&|^%*+-=<>.")
_JS_REGEX_KINDS = ("start", "op", "kw", "block_end")
# B-LR-8: a '(' immediately after one of these words opens a
# control-flow head; its matching ')' ends at expression-start.
_JS_CONTROL_HEAD_WORDS = {"if", "while", "for", "with", "catch",
                          "switch"}
# B-LR-10 round 4 / B-LR-13 round 5: word tokens that may
# legally follow a string (or regex) literal — the full grammar
# inventory, not just the first three found: binary word
# operators (in / instanceof), the for-of separator (of),
# TypeScript type operators (as / satisfies, incl. chained
# 'as const' / 'as unknown as T' and satisfies records),
# the TS conditional-type keyword after a literal type
# (extends), and import-attribute keywords after a module
# specifier string (assert / with). Every other follow class
# is punctuator/operator/EOL, handled in
# _js_plausible_string_close. Used by the plausibility check
# in _js_regex_end (see _js_plausible_string_close).
_JS_STRING_FOLLOW_WORDS = {"in", "of", "instanceof", "as",
                           "satisfies", "extends", "assert",
                           "with"}


def _js_is_control_head(prev, word_member):
    return prev[1] in _JS_CONTROL_HEAD_WORDS and not word_member


def _js_paren_close_prev(is_control):
    """Prev-token after ')': control-head close -> expression
    start (an unbraced regex consequent may follow); any other
    close -> value (a following '/' is division)."""
    return ("start", ")") if is_control else ("value", ")")


def _js_asi_prev(prev):
    """B-LR-9: newline after a value / incdec token -> the next
    line starts a new expression context (ASI). Control-head
    words keep their token so 'if\\n(cond)' still parses as a
    head; operators / keywords are unaffected."""
    if prev[0] in ("value", "incdec") \
            and prev[1] not in _JS_CONTROL_HEAD_WORDS:
        return ("start", "\n")
    return prev


def _js_word_prev(word):
    if word in _JS_VALUE_WORDS:
        return ("value", word)
    if word in _JS_REGEX_WORDS:
        return ("kw", word)
    return ("value", word)


def _js_op_prev(op):
    if op in ("++", "--"):
        return ("incdec", op)
    if op in (")", "]"):
        return ("value", op)
    return ("op", op)


def _js_scan_op(text, j):
    """(op_text, end) for the operator/punctuator at j, or None."""
    for op in _JS_MULTI_OPS:
        if text.startswith(op, j):
            if op == "?." and j + 2 < len(text) \
                    and text[j + 2].isdigit():
                return ("?", j + 1)  # '?' + '.5' numeric literal
            return (op, j + len(op))
    if text[j] in _JS_SINGLE_OPS:
        return (text[j], j + 1)
    return None


def _js_brace_is_object(prev):
    """True when '{' at prev opens an object literal (a value),
    False when it opens a block (statement body)."""
    kind, txt = prev
    if kind in ("value", "incdec", "start", "block_end"):
        return False
    if txt in (")", "]", ";", "else", "do", "try", "finally"):
        return False
    return True


def _js_plausible_string_close(text, end):
    """B-LR-10 round 4 / B-LR-13 round 5: True when the token
    after a candidate string close (index just past the closing
    quote) can legally follow a string literal in code — end of
    line/input, an operator or punctuator (incl. , ; ) ] }
    closes, ternary ?/:, member '.', call '(', tagged-template
    backtick), or a word token from the full follow inventory
    _JS_STRING_FOLLOW_WORDS (in / of / instanceof / TS as /
    satisfies / extends / assert / with). An identifier / number
    start outside that inventory means 'end' was
    really a later string's OPENING quote (its content follows),
    so the candidate quote is regex pattern content, not a
    string opener: /'/ must not 'close' at require('x')'s quote."""
    k, n = end, len(text)
    while k < n and text[k] in " \t\r":
        k += 1
    if k >= n or text[k] == "\n":
        return True
    if text[k].isalnum() or text[k] in "_$":
        m = _JS_IDENT_RE.match(text, k)
        return bool(m) and m.group(0) in _JS_STRING_FOLLOW_WORDS
    return True


def _js_template_balanced(text, start, end, strict=False):
    """B-LR-10 round 4 / round 5 (residual 3): True when
    text[start:end] (a candidate template body) has balanced
    ${ } interpolations. Round 5: only ${-opened braces are
    tracked (with plain-{ nesting inside an interpolation) —
    a raw '}' or '{' in template TEXT is ordinary text and
    unbalances nothing, so a template operand like
    `a}b/c ...` (balanced ${}, raw } in text) IS balanced.
    Strings / nested templates inside an interpolation are
    skipped whole so their braces cannot miscount.
    strict=True (regex scan running inside an enclosing ${ },
    via _find_js_expr_end) keeps the round-4 rule: a '}' at
    depth 0 there is the ENCLOSING interpolation's close, not
    template text (e.g. the /`/ literal inside
    `${/`/.source}`), so the body is unbalanced pattern
    content."""
    if strict:
        depth, k = 0, start
        while k < end:
            if text[k] == "\\":
                k += 2
                continue
            if text[k] == "$" and k + 1 < end \
                    and text[k + 1] == "{":
                depth += 1
                k += 2
                continue
            if text[k] == "}":
                if depth == 0:
                    return False
                depth -= 1
            k += 1
        return depth == 0
    braces, k = [], start
    while k < end:
        if text[k] == "\\":
            k += 2
            continue
        if braces and text[k] in "'\"":
            k = min(_find_js_string_end(text, k), end)
            continue
        if braces and text[k] == "`":
            k = min(_find_js_template_end(text, k), end)
            continue
        if text[k] == "$" and k + 1 < end and text[k + 1] == "{":
            braces.append("${")
            k += 2
            continue
        if braces and text[k] == "{":
            braces.append("{")
            k += 1
            continue
        if text[k] == "}":
            if braces:
                braces.pop()
            # else: raw '}' in template text — not a close.
            k += 1
            continue
        k += 1
    return not braces


def _js_regex_coherent_end(text, i):
    """B-LR-10 round 5 (residual 1), longest-coherent-span:
    rescan the putative regex span at i treating every quote
    as pattern content (quoted pairs are skipped whole, so a
    quote-pair spanning a '/' does not end the span at that
    slash; escapes and [...] classes honoured). Return the
    span end (closing '/' + flags) when the FIRST closing
    slash the scan reaches is followed by a legal regex-follow
    token (see _js_plausible_string_close — a regex literal is
    a value, so the follow inventory is the same); None when
    the scan reaches EOL/EOF without closing, or that first
    close's follow is incoherent (an identifier start that is
    not a follow word) — the regex reading then fails and
    string precedence may fire instead."""
    j, n = i + 1, len(text)
    in_class = False
    while j < n:
        c = text[j]
        if c == "\n":
            return None
        if c == "\\":
            j += 2
            continue
        if in_class:
            if c == "]":
                in_class = False
            j += 1
            continue
        if c == "[":
            in_class = True
            j += 1
            continue
        if c in "'\"":
            k, closed = j + 1, None
            while k < n and text[k] != "\n":
                if text[k] == "\\":
                    k += 2
                    continue
                if text[k] == c:
                    closed = k + 1
                    break
                k += 1
            j = closed if closed is not None else j + 1
            continue
        if c == "`":
            end = _find_js_template_end(text, j)
            closed_tpl = end < n or (end == n and end > j + 1
                                     and text[end - 1] == "`")
            j = end if closed_tpl else j + 1
            continue
        if c == "/":
            j += 1
            while j < n and (text[j].isalnum() or text[j] in "_$"):
                j += 1  # trailing flags
            return j if _js_plausible_string_close(text, j) else None
        j += 1
    return None


def _js_regex_end(text, i, tpl_strict_brace=False):
    """Index just past the regex literal at i (flags consumed),
    honouring \\ escapes and [...] classes (a '/' inside a class
    does not close). None when unterminated on the line.
    B-LR-10 string precedence, round 4 INVERTED: a quote met
    while scanning the span — in ANY operator/expression
    context, at span start, or as the first pattern char — is
    presumed a code string opener (the span is a misjudged
    division tail) unless provably pattern content: escaped,
    inside a class, unpaired on the line, or implausible as a
    string close (see _js_plausible_string_close). A presumed
    string whose segment contains a '/' ends the span at the
    string's closing quote — string content stays masked and a
    misjudged span can never expose a string tail as code. A
    slash-free quoted segment is skipped as pattern content
    (e.g. the require('...') inside a genuine /.../ literal).
    /'/ is safe: its quote's close-scan lands on the next
    string's opening quote, which fails plausibility, so the
    quote stays pattern content and the regex closes at '/'."""
    j, n = i + 1, len(text)
    in_class = False
    while j < n:
        c = text[j]
        if c == "\n":
            return None
        if c == "\\":
            j += 2
            continue
        if in_class:
            if c == "]":
                in_class = False
            j += 1
            continue
        if c == "[":
            in_class = True
            j += 1
            continue
        if c in "'\"":
            k, closed = j + 1, None
            while k < n and text[k] != "\n":
                if text[k] == "\\":
                    k += 2
                    continue
                if text[k] == c:
                    closed = k + 1
                    break
                k += 1
            if closed is not None \
                    and "/" in text[j + 1:closed - 1]:
                if _js_plausible_string_close(text, closed):
                    # Round 5, longest-coherent-span (B-LR-10
                    # residual 1): if the quote-as-pattern
                    # reading still closes this span coherently
                    # PAST this pair (e.g. /x'b/c' + tail/ —
                    # the pair's close merely happens to be
                    # operator-followed), the regex reading
                    # wins and the whole span is the literal.
                    coherent = _js_regex_coherent_end(text, i)
                    if coherent is not None and coherent > closed:
                        return coherent
                    return closed  # string wins; mask thru its end
                j += 1  # pattern quote (e.g. /'/): ordinary char
                continue
            if closed is not None:
                j = closed  # slash-free quoted fragment: skip pair
                continue
            j += 1  # unpaired quote: ordinary pattern char
            continue
        if c == "`":
            # Same precedence for template literals (the third
            # string form): a template operand in a misjudged
            # division tail is presumed code, not pattern content.
            end = _find_js_template_end(text, j)
            closed_tpl = end < n or (end == n and end > j + 1
                                     and text[end - 1] == "`")
            if closed_tpl and "/" in text[j + 1:end - 1]:
                if _js_plausible_string_close(text, end) \
                        and _js_template_balanced(
                            text, j + 1, end - 1,
                            strict=tpl_strict_brace):
                    # Same longest-coherent-span rule as the
                    # quote branch (round 5): a pattern reading
                    # closing coherently past this template wins.
                    coherent = _js_regex_coherent_end(text, i)
                    if coherent is not None and coherent > end:
                        return coherent
                    return end  # template wins; mask thru its end
                j += 1  # pattern backtick: ordinary char
                continue
            if closed_tpl:
                j = end  # slash-free template fragment: skip it
                continue
            j += 1  # unterminated template: ordinary char
            continue
        if c == "/":
            j += 1
            while j < n and (text[j].isalnum() or text[j] in "_$"):
                j += 1  # trailing flags
            return j
        j += 1
    return None


def _find_js_expr_end(text, i):
    """Index just past the } matching the ${ opened before i.
    Regex-aware: a regex literal inside the expression is skipped
    whole, so its braces/backticks/quotes cannot miscount depth."""
    depth, j, n = 1, i, len(text)
    prev = ("start", "")
    braces = []
    parens = []
    word_member = False
    while j < n:
        c = text[j]
        if c.isspace():
            if c == "\n":
                prev = _js_asi_prev(prev)
            j += 1
            continue
        if text.startswith("//", j):
            k = text.find("\n", j)
            j = n if k < 0 else k
            continue
        if text.startswith("/*", j):
            k = text.find("*/", j + 2)
            j = n if k < 0 else k + 2
            continue
        if c in "'\"":
            j = _find_js_string_end(text, j)
            prev = ("value", "str")
            continue
        if c == "`":
            j = _find_js_template_end(text, j)
            prev = ("value", "tpl")
            continue
        if c == "/":
            end = _js_regex_end(text, j, tpl_strict_brace=True) \
                if prev[0] in _JS_REGEX_KINDS else None
            if end is not None:
                j, prev = end, ("value", "re")
                continue
            if prev[0] in _JS_REGEX_KINDS:  # unterminated: resync EOL
                k = text.find("\n", j)
                j = n if k < 0 else k
                prev = ("value", "re")
                continue
            j += 2 if text.startswith("/=", j) else 1
            prev = ("op", "/")
            continue
        if c == "{":
            braces.append(_js_brace_is_object(prev))
            depth += 1
            prev = ("op", "{") if braces[-1] else ("start", "{")
            j += 1
            continue
        if c == "}":
            depth -= 1
            j += 1
            if depth == 0:
                return j
            is_obj = braces.pop() if braces else False
            prev = ("value", "}") if is_obj else ("block_end", "}")
            continue
        m = _JS_IDENT_RE.match(text, j)
        if m:
            word_member = prev[1].endswith(".")
            prev = _js_word_prev(m.group(0))
            j = m.end()
            continue
        m = _JS_NUMBER_RE.match(text, j)
        if m:
            prev = ("value", "num")
            word_member = False
            j = m.end()
            continue
        op = _js_scan_op(text, j)
        if op:
            if op[0] == "(":
                parens.append(_js_is_control_head(prev, word_member))
                prev = ("op", "(")
            elif op[0] == ")":
                prev = _js_paren_close_prev(
                    parens.pop() if parens else False)
            else:
                prev = _js_op_prev(op[0])
            word_member = False
            j = op[1]
            continue
        j += 1
    return n


def _find_js_template_end(text, i):
    j, n = i + 1, len(text)
    while j < n:
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == "`":
            return j + 1
        if text[j] == "$" and j + 1 < n and text[j + 1] == "{":
            j = _find_js_expr_end(text, j + 2)
            continue
        j += 1
    return n


# A string literal is KEPT (not blanked) only when the masked code
# immediately before it is an import context — require( / import /
# from — so the import regex can still read the real specifier.
_JS_IMPORT_CTX = re.compile(r"\b(?:require\s*\(\s*|import\s*\(?\s*|from\s*)$")


def _mask_js(text):
    """Blank // and /* */ comments, template literals, regex
    literals, and string literals that are not import specifiers
    (see _JS_IMPORT_CTX). Regex vs division is decided by the
    previous-significant-token heuristic (see _JS_REGEX_KINDS);
    comments take lexical precedence ('//' and '/*' can never
    open a valid regex, whose first pattern char cannot be an
    unescaped '*' and whose body cannot be empty)."""
    out = list(text)
    i, n = 0, len(text)
    prev = ("start", "")
    braces = []
    parens = []
    word_member = False
    while i < n:
        c = text[i]
        if c.isspace():
            if c == "\n":
                prev = _js_asi_prev(prev)
            i += 1
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            _blank(out, text, i, j)
            i = j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            _blank(out, text, i, j)
            i = j
            continue
        if c in "'\"":
            j = _find_js_string_end(text, i)
            tail = "".join(out[max(0, i - 128):i])
            if not _JS_IMPORT_CTX.search(tail):
                _blank(out, text, i, j)
            i = j
            prev = ("value", "str")
            continue
        if c == "`":
            j = _find_js_template_end(text, i)
            _blank(out, text, i, j)
            i = j
            prev = ("value", "tpl")
            continue
        if c == "/":
            end = _js_regex_end(text, i) \
                if prev[0] in _JS_REGEX_KINDS else None
            if end is not None:
                _blank(out, text, i, end)
                i, prev = end, ("value", "re")
                continue
            if prev[0] in _JS_REGEX_KINDS:
                # Regex position but no closing '/' on the line:
                # phantom-safe — blank to EOL, resync at newline.
                j = text.find("\n", i)
                j = n if j < 0 else j
                _blank(out, text, i, j)
                i, prev = j, ("value", "re")
                continue
            i += 2 if text.startswith("/=", i) else 1  # division
            prev = ("op", "/")
            continue
        if c == "{":
            braces.append(_js_brace_is_object(prev))
            prev = ("op", "{") if braces[-1] else ("start", "{")
            i += 1
            continue
        if c == "}":
            is_obj = braces.pop() if braces else False
            prev = ("value", "}") if is_obj else ("block_end", "}")
            i += 1
            continue
        m = _JS_IDENT_RE.match(text, i)
        if m:
            word_member = prev[1].endswith(".")
            prev = _js_word_prev(m.group(0))
            i = m.end()
            continue
        m = _JS_NUMBER_RE.match(text, i)
        if m:
            prev = ("value", "num")
            word_member = False
            i = m.end()
            continue
        op = _js_scan_op(text, i)
        if op:
            if op[0] == "(":
                parens.append(_js_is_control_head(prev, word_member))
                prev = ("op", "(")
            elif op[0] == ")":
                prev = _js_paren_close_prev(
                    parens.pop() if parens else False)
            else:
                prev = _js_op_prev(op[0])
            word_member = False
            i = op[1]
            continue
        i += 1
    return "".join(out)


def scan_imports(lang, lines):
    out = []
    for rx_lang, rx in IMPORT_RES:
        if rx_lang != lang:
            continue
        text = "\n".join(lines)
        if lang == "Python":
            text = _mask_python(text)
        elif lang in ("JavaScript", "TypeScript"):
            text = _mask_js(text)
        for i, raw in enumerate(text.split("\n"), 1):
            m = rx.search(raw)
            if m:
                out.append((m.group(1), i, raw.strip()[:160]))
    return out


# ------------------------------------------------------------ scanner
def _probe(fn, what):
    """B-LR-4: every path probe maps OS-level failure (ENAMETOOLONG,
    ELOOP, embedded NUL, ...) to a named ToolError — a bare OSError
    must never escape as a -32603 on the tool surface."""
    try:
        return fn()
    except (OSError, ValueError, RuntimeError) as exc:
        raise ToolError(
            f"TARGET_PATH_INVALID: {what} cannot be probed "
            f"({exc.__class__.__name__})") from None


def _symlink_report(full, rel, root_real):
    resolved = _probe(full.resolve, f"symlink {rel!r}")
    link_target = _probe(lambda: os.readlink(full), f"symlink {rel!r}")
    escape = not str(resolved).startswith(str(root_real) + os.sep) \
        and resolved != root_real
    return {"path": rel, "kind": "symlink",
            "link_target": link_target,
            "resolved": str(resolved), "escape": escape,
            "traversed": False,
            "evidence": _ev(rel, "symlink entry; never traversed by scanner")}


def scan_target(args):
    if not isinstance(args, dict):
        raise ToolError("ARGUMENTS_INVALID: arguments must be an object")
    path = args.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ToolError("TARGET_PATH_INVALID: path must be a non-empty string")
    max_files = MAX_FILES_DEFAULT
    if args.get("max_files") is not None:
        max_files = coerce_int_param(args["max_files"], "max_files",
                                     "MAX_FILES_INVALID")
        if max_files < 1 or max_files > MAX_FILES_HARD:
            raise ToolError(
                f"MAX_FILES_INVALID: max_files must be 1..{MAX_FILES_HARD}")
    root = Path(path)
    exists = _probe(root.exists, "target path")
    is_link = _probe(root.is_symlink, "target path")
    if not exists and not is_link:
        raise ToolError(f"TARGET_NOT_FOUND: no such path: {path}")
    if not _probe(root.is_dir, "target path"):
        raise ToolError(f"TARGET_NOT_DIRECTORY: not a directory: {path}")
    root_real = _probe(root.resolve, "target path")

    files = []            # (rel, abs, size)
    symlink_reports = []  # every symlink; escapes flagged
    skipped_dirs = []
    nonregular_count = 0  # B-LR-11: FIFO/socket/device children
    truncated = False
    trunc_reasons = []

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        filenames = sorted(filenames)
        rel_dir = Path(dirpath).relative_to(root)
        keep = []
        for d in dirnames:
            full = Path(dirpath) / d
            rel = str(rel_dir / d) if str(rel_dir) != "." else d
            if _probe(full.is_symlink, f"path {rel!r}"):
                symlink_reports.append(_symlink_report(full, rel, root_real))
                continue
            if d in SKIP_DIRS:
                skipped_dirs.append(rel)
                continue
            keep.append(d)
        dirnames[:] = keep
        for fn in filenames:
            full = Path(dirpath) / fn
            rel = str(rel_dir / fn) if str(rel_dir) != "." else fn
            if _probe(full.is_symlink, f"path {rel!r}"):
                symlink_reports.append(_symlink_report(full, rel, root_real))
                continue
            if len(files) >= max_files:
                truncated = True
                if "MAX_FILES_REACHED" not in trunc_reasons:
                    trunc_reasons.append("MAX_FILES_REACHED")
                continue
            # B-LR-11: gate ALL reads to regular files (lstat, no
            # follow). A FIFO/socket/device passes a size gate at
            # 0 bytes yet blocks forever on open; such children
            # are skipped + counted, never opened.
            try:
                st = full.lstat()
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode):
                nonregular_count += 1
                continue
            files.append((rel, full, st.st_size))

    if not files:
        raise ToolError("TARGET_EMPTY: directory contains no regular files "
                        "(outside skipped dirs / symlinks)")

    local_roots = set()
    for r, _, _ in files:
        local_roots.add(Path(r).parts[0].split(".")[0])
        local_roots.add(Path(r).stem)
    lang_files, lang_loc = {}, {}
    binary_count = 0
    total_loc = 0
    test_files, test_loc = [], 0
    entry_points, layers, packages = [], {}, []
    manifests_found = []
    declared, observed, inferred = [], [], []
    runtime_specs, unknowns = [], []
    internal_imports = {}   # module -> list of (importer_rel, line)
    file_lines_cache = {}

    for rel, full, size in files:
        name = Path(rel).name
        lang = EXT_LANG.get(Path(rel).suffix.lower())
        is_manifest = name in MANIFEST_NAMES
        if is_manifest:
            manifests_found.append(rel)
            parse_manifest(rel, full, declared, runtime_specs, unknowns)
        # binary / size gate for text parsing
        raw_bytes = None
        if size <= MAX_TEXT_BYTES:
            try:
                raw_bytes = full.read_bytes()
            except OSError:
                raw_bytes = None
        if raw_bytes is None:
            if size > MAX_TEXT_BYTES:
                trunc_reasons.append("FILE_TOO_LARGE_SKIPPED_TEXT")
            continue
        if b"\x00" in raw_bytes[:8192]:
            binary_count += 1
            continue
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            binary_count += 1
            continue
        lines = text.splitlines()
        file_lines_cache[rel] = lines
        loc = len(lines)
        if lang:
            lang_files[lang] = lang_files.get(lang, 0) + 1
            lang_loc[lang] = lang_loc.get(lang, 0) + loc
            total_loc += loc
        if _is_test(rel):
            test_files.append(rel)
            test_loc += loc
        if name in ENTRY_NAMES:
            entry_points.append({
                "path": rel,
                "evidence": _ev(rel, f"filename matches entry-point convention: {name}")})
        parts = Path(rel).parts[:-1]
        for part in parts:
            if part.lower() in LAYER_DIRS:
                layers.setdefault(LAYER_DIRS[part.lower()],
                                  {"layer": LAYER_DIRS[part.lower()],
                                   "evidence": _ev(rel, f"directory component '{part}' in path")})
        if name == "__init__.py":
            packages.append({"path": str(Path(rel).parent),
                             "kind": "python-package",
                             "evidence": _ev(rel, "__init__.py present in directory")})
        if lang in ("Python", "JavaScript", "TypeScript", "Go", "Ruby", "Java", "PHP"):
            for mod, ln, raw_line in scan_imports(lang, lines):
                root_mod = mod.split("/")[0].split(".")[0]
                stdlib = (lang == "Python" and root_mod in PY_STDLIB) \
                    or (lang in ("JavaScript", "TypeScript") and root_mod in JS_BUILTINS)
                if stdlib:
                    continue
                # internal module? file/dir of that name in tree
                observed.append({
                    "name": mod, "ecosystem": lang.lower(),
                    "source_class": "OBSERVED",
                    "internal": root_mod in local_roots,
                    "evidence": _ev(rel, f"import statement: {raw_line}", ln)})
                if lang == "Python":
                    internal_imports.setdefault(root_mod, []).append((rel, ln))
                    tail = mod.replace("/", ".").split(".")[-1]
                    if tail != root_mod:
                        internal_imports.setdefault(tail, []).append((rel, ln))
                    if root_mod in DIST_MAP:
                        inferred.append({
                            "name": DIST_MAP[root_mod],
                            "source_class": "INFERRED",
                            "basis": f"import root '{root_mod}' maps to distribution '{DIST_MAP[root_mod]}' via built-in mapping table",
                            "evidence": _ev(rel, f"import statement: {raw_line}", ln)})
        # runtime version files
        if name == ".python-version" and lines:
            runtime_specs.append(("python", "python", lines[0].strip(),
                                  _ev(rel, f".python-version: {lines[0].strip()}", 1)))
        if name == ".nvmrc" and lines:
            runtime_specs.append(("node", "node", lines[0].strip().lstrip("v"),
                                  _ev(rel, f".nvmrc: {lines[0].strip()}", 1)))
        if name == ".ruby-version" and lines:
            runtime_specs.append(("ruby", "ruby", lines[0].strip(),
                                  _ev(rel, f".ruby-version: {lines[0].strip()}", 1)))
        if name == "runtime.txt" and lines:
            m = re.match(r"python-(\S+)", lines[0].strip())
            if m:
                runtime_specs.append(("python", "python", m.group(1),
                                      _ev(rel, f"runtime.txt: {lines[0].strip()}", 1)))

    # dedupe observed by (name, path, line) kept; aggregate counts
    risks = []
    for kind, eco_name, ver, ev in runtime_specs:
        if kind in ("python", "node", "php", "ruby"):
            hit = eol_check("runtime", kind, kind, ver, ev)
            if hit:
                risks.append(hit)
            if ver:
                risks.append({"kind": "RUNTIME_PINNED", "subject": kind,
                              "version": ver, "evidence": ev})
    declared_names = {(d["name"].lower(), d["ecosystem"]) for d in declared}
    for d in declared:
        hit = eol_check("package", d["ecosystem"], d["name"],
                        d["version"], d["evidence"])
        if hit:
            risks.append(hit)
        if d["version"] is None or str(d["version"]).strip() in ("*", "latest", ""):
            risks.append({"kind": "UNPINNED_VERSION", "subject": d["name"],
                          "version": d["version"],
                          "detail": "Declared with no pinned version; resolved version is not determinable statically.",
                          "evidence": d["evidence"]})
    # observed-but-undeclared -> INFERRED undeclared dependency (labeled)
    seen_inferred_undeclared = set()
    for o in observed:
        key = (o["name"].split("/")[0].split(".")[0].lower(), o["evidence"]["path"])
        base = o["name"].split("/")[0].split(".")[0]
        if o["ecosystem"] == "python" and base not in DIST_MAP \
                and (base.lower(), "python") not in declared_names \
                and base not in local_roots \
                and key not in seen_inferred_undeclared:
            seen_inferred_undeclared.add(key)
            inferred.append({
                "name": base, "source_class": "INFERRED",
                "basis": "import observed in code but no matching DECLARED entry in any parsed manifest; treated as inferred undeclared dependency, not as a declared fact",
                "evidence": o["evidence"]})

    if not runtime_specs or all(v is None for _, _, v, _ in runtime_specs):
        unknowns.append({"item": "primary runtime version", "status": "UNKNOWN",
                         "reason": "no runtime version pin found in .python-version/.nvmrc/.ruby-version/runtime.txt/engines/requires-python/pom.xml"})
    if not test_files:
        unknowns.append({"item": "test suite", "status": "UNKNOWN",
                         "reason": "no files matched test naming/path conventions; absence of tests is not asserted — only that none were found statically"})
    unknowns.append({"item": "database / external services", "status": "UNKNOWN",
                     "reason": "not determinable from static structure alone in v0.1; no config-value inference is performed"})
    unknowns.append({"item": "CI / deployment configuration", "status": "UNKNOWN",
                     "reason": "not assessed in v0.1 recon scope"})
    unknowns.append({"item": "manifest age (commit history)", "status": "UNKNOWN",
                     "reason": "git history is not read in v0.1; only filesystem mtimes are reported as inputs"})

    # coupling hotspots: fan-in = distinct importers of an internal module
    hotspots = []
    local_modules = {Path(r).stem for r, _, _ in files if r.endswith(".py")}
    for mod, refs in sorted(internal_imports.items(),
                            key=lambda kv: -len({r for r, _ in kv[1]})):
        if mod in local_modules and len({r for r, _ in refs}) >= 1:
            importers = sorted({r for r, _ in refs})
            hotspots.append({
                "module": mod, "fan_in": len(importers),
                "evidence": _ev(importers[0],
                                f"imported by {len(importers)} file(s): {', '.join(importers[:5])}",
                                refs[0][1])})
    hotspots = hotspots[:10]

    manifest_inputs = []
    for rel in manifests_found:
        full = next(f for r, f, _ in files if r == rel)
        try:
            mt = datetime.fromtimestamp(full.stat().st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            mt = None
        manifest_inputs.append({"path": rel, "mtime_utc": mt,
                                "evidence": _ev(rel, "manifest file present; mtime is a filesystem signal, not commit age")})

    size_dist = {"small_lt_10kb": 0, "medium_10k_100k": 0, "large_gt_100k": 0}
    for _, _, s in files:
        if s < 10_000:
            size_dist["small_lt_10kb"] += 1
        elif s <= 100_000:
            size_dist["medium_10k_100k"] += 1
        else:
            size_dist["large_gt_100k"] += 1

    architecture = {
        "languages": [{"language": k, "files": lang_files[k], "loc": lang_loc[k],
                       "evidence": _ev(f"({lang_files[k]} files)",
                                       f"file extension census for {k}: {lang_files[k]} file(s), {lang_loc[k]} LOC")}
                      for k in sorted(lang_files, key=lambda x: -lang_loc[x])],
        "entry_points": entry_points,
        "packages": packages,
        "layers": sorted(layers.values(), key=lambda x: x["layer"]),
        "manifests": [{"path": r, "ecosystem": MANIFEST_NAMES[Path(r).name],
                       "evidence": _ev(r, "manifest file present")} for r in manifests_found],
        "file_count": len(files), "size_distribution": size_dist,
        "skipped_dirs": skipped_dirs,
    }
    return {
        "target": str(root_real),
        "descriptor": DESCRIPTOR,
        "architecture": architecture,
        "dependencies": {"declared": declared, "observed": observed,
                         "inferred": inferred},
        "risks": risks,
        "runtime_specs": [{"kind": k, "name": n, "version": v, "evidence": e}
                          for k, n, v, e in runtime_specs if k in
                          ("python", "node", "php", "ruby", "java", "go")],
        "modernization_inputs": {
            "loc_by_language": lang_loc, "total_loc": total_loc,
            "test_files": test_files, "test_loc": test_loc,
            "test_loc_ratio": round(test_loc / total_loc, 4) if total_loc else None,
            "manifests": manifest_inputs,
            "coupling_hotspots_fan_in": hotspots,
            "note": "Raw inputs for an estimator — NOT an estimate. No effort, cost, or duration figure is produced."},
        "unknowns": unknowns,
        "symlinks": symlink_reports,
        "binary_files_skipped": binary_count,
        "non_regular_files_skipped": nonregular_count,
        "truncated": truncated or bool(trunc_reasons),
        "truncation_reasons": sorted(set(trunc_reasons)),
        "eol_rules_version": EOL_RULES_VERSION,
        "scan_limits": {"max_files": max_files, "max_text_bytes": MAX_TEXT_BYTES},
    }


def architecture_map(args):
    full = scan_target(args)
    return {"target": full["target"], "descriptor": DESCRIPTOR,
            "architecture": full["architecture"],
            "unknowns": full["unknowns"], "truncated": full["truncated"],
            "truncation_reasons": full["truncation_reasons"]}


def dependency_risk_list(args):
    full = scan_target(args)
    return {"target": full["target"], "descriptor": DESCRIPTOR,
            "dependencies": full["dependencies"], "risks": full["risks"],
            "runtime_specs": full["runtime_specs"],
            "eol_rules_version": full["eol_rules_version"],
            "unknowns": full["unknowns"], "truncated": full["truncated"],
            "truncation_reasons": full["truncation_reasons"]}


def modernization_inputs(args):
    full = scan_target(args)
    return {"target": full["target"], "descriptor": DESCRIPTOR,
            "modernization_inputs": full["modernization_inputs"],
            "unknowns": full["unknowns"], "truncated": full["truncated"],
            "truncation_reasons": full["truncation_reasons"]}

# Eclipse Legacy Recon MCP · © 2026 Cyan Eclipse Technologies LLC · cetech.ai
