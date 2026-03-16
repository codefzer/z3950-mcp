## Commands

```bash
pip install -r requirements.txt   # install deps
pytest tests/ -v                  # run all 90 tests (always do this after changes)
python3 server.py                 # start MCP server
```

## Architecture

Three layers:
- `z3950_protocol/` — extracted PyZ3950 modules (pure Python Z39.50 protocol, do not modify)
- `z3950_client/` — async connection pool, MARC record processor, CCL query builder
- `tools/` — one file per MCP tool (search, holdings, details, browse, export)
- `server.py` — FastMCP entry point, registers all tools and resources
- `config/libraries.json` — pre-configured library systems (loc, worldcat, i-share, alma-template)

## Key Gotchas

- LOC's Z39.50 server returns `zoom_record.data` as `str`, not `bytes`. Must encode with `.encode('latin-1')` before parsing as binary MARC. Handled in `z3950_client/record_processor.py:parse_zoom_record`.
- `conn.databaseName` is the server-side Z39.50 database name (e.g. `"Voyager"`), NOT the config key (e.g. `"loc"`). Use `res['library_id']` from pool results for user-facing library IDs.
- `MARCReader` is a lazy iterator — use `next(iter(reader), None)` to read only the first record. `list(reader)` forces full decode of all records.
- `pymarc` 5.x: `.title` and `.author` are properties, not methods — do not call them with `()`.
- All blocking Z39.50 I/O must be wrapped in `asyncio.to_thread()` — never call `conn.search()` or `conn.close()` directly on the event loop.
- `pytest-asyncio` runs in strict mode — async tests need `@pytest.mark.asyncio`.

## Testing

Run `pytest tests/ -v` after any code change. All 90 tests must pass. Never mark a task complete with failing tests.

## Claude Desktop Integration

```json
{
  "mcpServers": {
    "z3950": {
      "command": "python3",
      "args": ["/Users/sam/Documents/GitHub/Z3950/server.py"]
    }
  }
}
```

## Constraints

- Do NOT use non-existent Claude Code features (e.g. `/plugin`, marketplace installs). If unsure whether a feature exists, say so.
- `z3950_protocol/` is vendored external code — do not refactor it.
