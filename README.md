# Eclipse Legacy Recon MCP

**Powered by Cyan Eclipse Technologies** — https://cetech.ai

**Point an agent at a codebase: architecture map, dependency/EOL risk list, modernization estimate inputs.**

## Status — honest labels

v0.1.0, **local, read-only**. MCP over stdio, Python stdlib only. No certification claimed — **bench pending**. Catalog entry: `legacy-recon-mcp` (spec sketch: `mcp-product-slate-20261023.md` §5). Free; services-led assessment funnel into CETech's legacy modernization line.

## Novel mechanism — evidence-bound recon

Every claim in the map and risk list cites a file path plus the manifest line or structural fact it rests on. Anything not determinable statically reports **UNKNOWN with the reason** — never a guessed stack. The dependency inventory distinguishes, in separate lists that are never blended:

- **DECLARED** — parsed from a manifest, with the manifest line as evidence.
- **OBSERVED** — import statements in code, with file + line as evidence (internal imports flagged `internal`).
- **INFERRED** — labeled inference with its basis stated (e.g. import root `PIL` → distribution `Pillow` via a built-in mapping table; an import with no matching declared entry → inferred undeclared dependency).

## Tools

`recon_scan` (full report) · `architecture_map` · `dependency_risk_list` · `modernization_inputs`

All take `path` (required string) and optional `max_files` (integer, 1–50000, default 5000, via the house `coerce_int_param` guard pattern).

**Modernization outputs are INPUTS, not an estimate:** LOC by language, test file presence / test-LOC ratio, manifest filesystem-mtime signals (explicitly *not* commit age — git history is UNKNOWN in v0.1), and coupling hotspots by fan-in. No effort, cost, or duration figure is produced.

## Manifests + EOL rules supported

Manifest parsers: `requirements.txt`, `Pipfile`, `pyproject.toml`, `setup.py`/`setup.cfg` (python_requires), `package.json`, `composer.json`, `Gemfile`, `pom.xml`, `go.mod`, `Cargo.toml`; runtime pins from `.python-version`, `.nvmrc`, `.ruby-version`, `runtime.txt`, `engines.node`, `requires-python`, pom `java.version`.

EOL risk comes only from a small, explicit, versioned-in-code rules table (`EOL_RULES_VERSION = 2026-10-25.1` in `recon_engine.py`): Python 2.7/3.6/3.7/3.8, Node 12/14/16/18, PHP 7.4/8.0, Ruby 2.7/3.0, Django 2.2/3.2/4.0/4.1, AngularJS 1.x, Rails 5.2/6.0, Flask 1.0. Every EOL claim cites its `rule_id`. No rule match = no claim (absence of a rule is never a claim of support). Unpinned declared versions surface as `UNPINNED_VERSION`.

## Safety

- Target code is **never executed, imported, or shelled out to**; no network calls.
- **Symlinks are never traversed** — every symlink is reported; one resolving outside the target tree is flagged `escape: true`.
- Binary files are skipped and counted, never parsed as text; files over 1 MB are not text-parsed.
- Caps fail visibly: hitting `max_files` sets `truncated: true` + `MAX_FILES_REACHED` — a truncated scan never presents as complete.
- Named, fail-closed refusals: `TARGET_NOT_FOUND`, `TARGET_NOT_DIRECTORY`, `TARGET_EMPTY`, `TARGET_PATH_INVALID`, `MAX_FILES_INVALID`, `ARGUMENTS_INVALID`. Malformed wire args are `-32602` naming the argument, never a raw `-32603`.
- VCS/cache/vendor dirs (`.git`, `__pycache__`, `node_modules`, `vendor`, …) are skipped and listed.

## Run it

```sh
python3 server.py                      # stdio
python3 -m unittest discover -s tests  # acceptance + schema fuzz
python3 smoke.py                       # subprocess stdio smoke
```

Fixtures: `fixtures/legacy-tree/` — synthetic mixed Python+JS legacy tree: Django 3.2 + Python 3.8 + Node 16 + AngularJS EOL pins, unpinned `requests`, a binary blob, and a symlink escape attempt (`escape_link` → `/etc`, recreated by tests/smoke if absent).

## Limitations (v0.1)

No lockfile parsing; no Gradle dependency extraction; no git history (manifest age = mtime only); DB/CI/deployment are UNKNOWN by design; EOL table is deliberately small and covers only its listed rules; import scanning is regex-based per language, not AST.

---

A Cyan Eclipse Technologies product. The "Powered by Cyan Eclipse Technologies" attribution travels with it.
