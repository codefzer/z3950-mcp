# Codebase Issue Triage: Proposed Tasks

## Accepted task proposal

Accepted: **Task 1 (Typo fix)** — align `export_marc_record` docs/examples to use
`export_format` consistently.

### Why this one first
- It is low-risk and user-facing.
- It removes copy/paste friction in examples immediately.
- It can be completed independently before larger behavioral changes.

### Planned implementation scope
- Update docs/examples that still use `format="binary"` for `export_marc_record(...)`.
- Verify the examples match the actual tool signature in `server.py`.

## 1) Typo fix task: align exported MARC parameter name in docs/examples

**Issue found**
- Multiple docs/examples use `format="binary"` for `export_marc_record(...)`, but the tool signature uses `export_format`.
- This is effectively an API keyword typo in user-facing examples and can cause invocation errors when copied verbatim.

**Evidence**
- `server.py` defines `export_marc_record(..., export_format: str = 'binary')`.
- `README.md`, `QUICKSTART.md`, and `IMPLEMENTATION_SUMMARY.md` show `format="binary"` examples.

**Proposed task**
- Standardize naming in docs and examples to match the real parameter (`export_format`), or add a backward-compatible alias `format` in the tool layer.

**Acceptance criteria**
- All user docs show one consistent parameter name.
- A copy/pasted example from docs runs without argument-name errors.

---

## 2) Bug fix task: enforce configured per-library timeouts during network operations

**Issue found**
- `config/libraries.json` defines `timeout` for each library, but query/scan/export paths do not appear to enforce it around blocking calls.
- In degraded network conditions, operations can block longer than expected despite timeout configuration being present.

**Evidence**
- `config/libraries.json` includes `timeout` for each library.
- `z3950_client/connection_pool.py` creates connections and executes operations but does not apply per-library timeout controls to searches/scans.

**Proposed task**
- Apply explicit timeout enforcement for blocking Z39.50 operations (e.g., `conn.search`, `conn.scan`, record fetch path), using `asyncio.wait_for` around thread-wrapped calls or protocol-level timeout settings where supported.

**Acceptance criteria**
- Operations return a timeout error close to configured limits.
- Timeout behavior is deterministic and logged with library ID.

---

## 3) Documentation discrepancy task: remove or implement claimed result caching

**Issue found**
- Docs claim query-result caching (e.g., 5-minute TTL), but code primarily shows connection reuse and library-config caching.
- This can mislead users/operators about expected performance and cache invalidation behavior.

**Evidence**
- `IMPLEMENTATION_SUMMARY.md` and `QUICKSTART.md` mention result caching/TTL.
- Search-related code in `tools/` and `z3950_client/` does not include a query-result cache implementation.

**Proposed task**
- Either (A) implement an actual query-result cache with explicit TTL and invalidation policy, or (B) update docs to accurately state only connection/config caching exists.

**Acceptance criteria**
- Docs and runtime behavior match.
- If cache is implemented, add observability fields (`cache_hit`, `cache_ttl_remaining`) or clear logs.

---

## 4) Test improvement task: add regression tests for documented tool-call examples

**Issue found**
- Existing tests are strong on core internals but do not explicitly guard against docs/example drift (e.g., wrong argument names in examples).

**Evidence**
- `tests/test_basic.py` exercises connection pool, query builder, MARC processing, and tool behavior, but there is no dedicated "docs examples are executable" regression test set.

**Proposed task**
- Add tests that validate tool entry-point signatures against docs examples (especially `export_marc_record` argument names) and expected error messages for invalid parameters.

**Acceptance criteria**
- A failing test reproduces current docs drift before fix.
- Updated tests pass after docs/signature alignment and remain in CI.
