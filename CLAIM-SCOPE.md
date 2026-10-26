# Eclipse Legacy Recon — spec errata and claim-narrowing note

**Status:** appended errata, 2026-10-26. The original product sketch
(`mcp-product-slate-20261023.md` §5) is not edited. This note narrows
the public and runtime claims for v0.1.0 to the scope actually
observed by the Eclipse Test Bench.

**Owner disposition:** narrow the claims to observed scope. Do not
stand the product as permanently FAILED, and do not run a fourth
fix round for the withdrawn classes below.

**Bench basis:** cards
`eclipse-legacy-recon-mcp-2026-10-26.json` through
`eclipse-legacy-recon-mcp-2026-10-26-10.json`. Card -10 remains the
latest bench record: **FAILED, 22/25, at the former universal JS/TS
claim**. Narrowing does not rewrite that verdict. Any certification
claim requires a later scoped re-bench against this narrowed scope.

## Interpretation rules

1. **Positive, scoped reports only.** Within the supported scope
   below, a reported DECLARED, OBSERVED, or INFERRED entry is a
   positive report with the evidence or basis carried in the output.
2. **No exhaustive-inventory claim.** OBSERVED is not a promise that
   every import in a tree was found. The recall withdrawals below
   are part of the claim, not footnotes to a stronger claim.
3. **Withdrawn shapes are outside the evidence claim.** An entry
   arising solely from a withdrawn shape is not a supported
   evidence-bound OBSERVED claim, even though the current lexer can
   still produce it. Every tool output therefore carries the
   structured `claim_scope` object from `recon_engine.CLAIM_SCOPE`.
4. **Standing UNKNOWN categories only.** The product reports the
   UNKNOWN categories implemented in the engine, with reasons. It
   does not claim a dedicated UNKNOWN entry for dynamic imports.
5. **No separate accuracy elevation for other import languages.**
   The bench-derived OBSERVED accuracy scope in this note is stated
   for Python and JavaScript/TypeScript. The engine also has import
   patterns for Go, Ruby, Java, and PHP, but this note does not
   elevate those patterns to a bench-observed accuracy claim.

## Supported claim set

### Product, transport, and safety

- Local, read-only, MCP-over-stdio recon through exactly four tools:
  `recon_scan`, `architecture_map`, `dependency_risk_list`, and
  `modernization_inputs`.
- Target code is not executed, imported, or shelled out to; the
  scanner makes no network calls.
- Binary and non-UTF-8 files are skipped and counted; files over
  1 MB are not text-parsed and are counted as oversize; hitting
  `max_files` sets the truncation flag rather than presenting the
  partial scan as complete.
- Ordinary symlinks are not traversed. A resolvable symlink is
  reported, and one resolving outside the target is flagged as an
  escape. The self-referential-loop exception is withdrawn below.
- Named target and argument refusals hold on the tool surface,
  including overlong-path shapes exercised by the bench.

### Architecture and modernization inputs

- Architecture reporting is limited to the scanned regular files:
  language census and LOC from the extension map, entry-point
  filename conventions, Python packages marked by `__init__.py`,
  directory-name layer signals, manifest presence, file count, and
  size distribution.
- Modernization output is **inputs only**: LOC by language, test-file
  presence and test-LOC ratio, manifest filesystem mtimes, and
  Python coupling hotspots by fan-in. It is not an effort, cost, or
  duration estimate.

### Manifests, runtime pins, and EOL

- DECLARED extraction is claimed only for the parsers listed in the
  README: `requirements.txt`, `Pipfile`, `pyproject.toml`,
  `setup.py`/`setup.cfg`, `package.json`, `composer.json`, `Gemfile`,
  `pom.xml`, `go.mod`, and `Cargo.toml`.
- Runtime-pin reporting is claimed only for the sources listed in
  the README.
- EOL claims come only from `EOL_RULES_VERSION = 2026-10-25.1` and
  cite a `rule_id`. No matching rule means no EOL claim; it is not a
  claim that a version is supported. An unpinned declared version
  is reported as `UNPINNED_VERSION`, not guessed into an EOL risk.

### Evidence separation and standing unknowns

- DECLARED (manifest), OBSERVED (code import statements), and
  INFERRED (labelled inference with basis) remain separate lists.
- The bench-verified separation cases include import-only,
  manifest-only, and `PIL` observed with `Pillow` inferred from the
  built-in mapping basis.
- Standing UNKNOWN-with-reason categories are the ones implemented
  by the engine, including missing runtime pin, no test files found
  by convention, database/external services, CI/deployment, and
  manifest commit age.

### Python OBSERVED accuracy

- Within the exercised Python scope, positive OBSERVED entries are
  supported for ordinary import forms while import-shaped text in
  strings, triple-quoted strings/docstrings, comments, raw and
  f-string forms exercised by cards -1 through -10 does not mint a
  supported phantom.
- Python coupling hotspots use the Python import graph actually
  extracted by the scanner; they inherit the recall limits below.

### JavaScript and TypeScript OBSERVED accuracy

Supported positive OBSERVED extraction covers the JavaScript and
TypeScript language surfaces exercised by the bench record,
including the `.js`, `.mjs`, `.ts`, and `.tsx` file surfaces named
there, in the shapes below. The engine also maps `.cjs` to
JavaScript and `.jsx` to JavaScript, but those suffixes were not
separately file-surface benched; no separate extension-specific
claim is made for them.

- ordinary `import`, `export ... from`, and `require` forms;
- strings, templates, and comments, including nested templates,
  escaped quotes, multiline templates, split-brace imports, and
  standalone or normally opened multiline block comments;
- regex literals in the iteratively verified families: escaped
  slashes and character classes; operator and control-head
  contexts; ASI line-leading positions; keyword-spelled division
  followed by string or template tails across the verified
  operator/follow matrices; longest-coherent closing-slash spans;
  raw-brace template operands; the card-8 **no-closing-slash**
  family; and the card-9 **same-line comment-opener** family.

This is a claim about those observed families. It is not a claim
that the heuristic JS/TS lexer is correct for every legal program.

## Withdrawn claims

The following claims are **withdrawn by name**. They must remain in
this withdrawn list; silently deleting them from claim positions is
not the narrowing.

### W1 — JS/TS multiline block-comment continuation after a split no-close span

Machine name: `JS_TS_MULTILINE_BLOCK_COMMENT_CONTINUATION_AFTER_SPLIT_NO_CLOSE_SPAN`.

Withdrawn: phantom-free JS/TS OBSERVED extraction when a block
comment's opening `/*` is the candidate closing slash of a preceding
no-closing-slash regex-like span and import-shaped text appears on
a continuation line of that block comment. Card -10 reproduced
false OBSERVED entries in JS, TS, and TSX/CRLF variants.

### W2 — JS/TS chained no-closing-slash regex-like spans

Machine name: `JS_TS_CHAINED_NO_CLOSING_SLASH_REGEX_SPANS_ON_ONE_LINE`.

Withdrawn: phantom-free JS/TS OBSERVED extraction when two or more
no-closing-slash regex-like spans are chained on one physical line
and a later span's import-shaped pattern tail can be lexed as code.
Card -10 reproduced the class with and without a comment tail.

### W3 — B-LR-14 invalid-line identifier-follow shapes

Machine name: `B_LR_14_INVALID_LINE_NONINVENTORY_IDENTIFIER_FOLLOW`.

Withdrawn: evidence-bound OBSERVED extraction on syntactically
invalid JS/TS lines where a misjudged string/regex span is followed
by a non-inventory or bare identifier follow. These lines are
outside the supported claim even though they are recorded in the
bench backlog as non-gating.

### W4 — Exhaustive OBSERVED recall

Machine name: `EXHAUSTIVE_OBSERVED_RECALL`.

Withdrawn: any claim that OBSERVED is exhaustive. The bench record
establishes at least these recall limits:

- JS/TS and Python extraction takes at most one regex match per
  physical line, so a second import/require on the same line can be
  missed.
- JS/TS `require(` or `import` split across physical lines can be
  missed.
- Python imports after a semicolon or another statement on the same
  line, the second module in a comma list, backslash-continued
  imports, and relative `from . import ...` / `from .mod import ...`
  forms can be missed.
- A raw-`}` template nested in `${...}`, and a no-closing-slash
  regex-like span inside a template `${...}`, can over-mask later
  text in the file and cause real imports to be missed (B-LR-15 and
  its card-9 adjacent observation).

### W5 — Dynamic-import observation and a specific dynamic UNKNOWN

Machine name: `DYNAMIC_IMPORT_OBSERVATION_OR_SPECIFIC_UNKNOWN`.

Withdrawn: any claim that static or variable dynamic imports are
OBSERVED, and any claim that the product emits a dedicated UNKNOWN
entry specifically naming dynamic imports. Dynamic imports are not
guessed; B-LR-3 remains a named limitation.

### W6 — `.mts` and `.cts` OBSERVED extraction

Machine name: `MTS_CTS_OBSERVED_EXTRACTION`.

Withdrawn: JS/TS OBSERVED extraction for `.mts` and `.cts`. Those
suffixes are not in the engine's `EXT_LANG` map; their files may be
counted as files, but no import extraction is claimed for them.

### W7 — Completeness over unreadable subtrees

Machine name: `PERMISSION_DENIED_SUBTREE_COMPLETENESS`.

Withdrawn: a completeness claim for a tree containing a
permission-denied subdirectory. The bench backlog records that such
a subtree can be omitted without `truncated: true` (B-LR-7).

### W8 — Report-and-skip treatment of self-referential symlink loops

Machine name: `SELF_REFERENTIAL_SYMLINK_REPORT_AND_SKIP`.

Withdrawn: the claim that every symlink is reported and skipped.
A self-referential in-tree symlink loop can abort the scan with
`TARGET_PATH_INVALID` instead (B-LR-7). Ordinary symlink reporting
and non-traversal remain supported as stated above.

### W9 — Hosted, authenticated, or multi-tenant operation

Machine name: `HOSTED_AUTHENTICATED_OR_MULTI_TENANT_OPERATION`.

Withdrawn: any hosted, authenticated, multi-tenant, or remote
operation claim. Card -10's U1 was not applicable because v0.1 is
local stdio only; process ownership is the boundary.

## Runtime fence choice

The withdrawn lexical classes are patterns inside otherwise valid
target trees. The product does **not** refuse an entire scan merely
because such a pattern may be present; that would withdraw verified
architecture, manifest, EOL, Python, and other JS/TS surfaces along
with the failed classes. Instead:

- the descriptor is narrowed on every tool surface;
- every successful tool output carries `claim_scope` with
  `status: NARROWED_TO_OBSERVED_SCOPE`, the supported positive
  claim, and the withdrawn classes by name;
- the README and Bazaar manifest carry the same boundary.

That labelling is the fence. No output may present OBSERVED as
universal, exhaustive, or evidence-bound for W1–W9.

## Mechanical re-bench contract

A scoped re-bench can check, without relying on prose judgment:

1. `recon_engine.DESCRIPTOR` contains `NARROWED OBSERVED SCOPE` and
   points to this file.
2. All four tool outputs contain the same structured `claim_scope`
   object, with W1 and W2 named in `withdrawn`.
3. `CLAIM-SCOPE.md`, the README, and `bazaar-manifest.json` name
   the same supported boundary and the same withdrawn classes.
4. The former universal phrases — “Every claim cites its evidence”
   and “Every claim cites a file path” — do not appear in claim
   positions in the README, manifest, engine descriptor, or server
   tool descriptions. They may appear only as identified historical
   or withdrawn wording.
5. The pre-existing suite remains green, and the claims-lint tests
   in `tests/test_claim_scope.py` pass.

---

Eclipse Legacy Recon MCP · © 2026 Cyan Eclipse Technologies LLC · cetech.ai
