# Quick Start Guide - Z39.50 MCP Server

Get up and running in 5 minutes.

## 1. Install Dependencies

```bash
cd /Users/sam/Documents/GitHub/Z3950
pip install -r requirements.txt
```

This installs:
- fastmcp: MCP server framework
- pymarc: MARC record processing
- ply: Query parser

## 2. Start the Server

```bash
python server.py
```

You should see:
```
Z39.50 MCP Server starting...
Available libraries: loc, worldcat, i-share
Tools registered: search_libraries, check_availability, ...
```

## 3. Test with Claude Desktop

### Option A: Manual Configuration
Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "z3950": {
      "command": "python",
      "args": ["/Users/sam/Documents/GitHub/Z3950/server.py"]
    }
  }
}
```

Then restart Claude Desktop.

### Option B: Test Directly
In a Python script or REPL:

```python
import asyncio
from tools.search import search_libraries
from z3950_client.connection_pool import AsyncConnectionPool

# Search for a book
result = asyncio.run(search_libraries(
    query="Hamlet",
    libraries=["loc"],  # Library of Congress
    query_type="title",
    max_results=5
))

print(f"Found {result['total_results']} results")
for book in result['results']:
    print(f"  - {book.get('title', 'Unknown')}")
```

## 4. Try These Example Searches

### Example 1: Search by Title
```
"Find books about The Great Gatsby from the Library of Congress"
→ search_libraries("The Great Gatsby", libraries="loc", query_type="title")
```

### Example 2: Search by Author
```
"Search for books by Stephen King across all libraries"
→ search_libraries("Stephen King", query_type="author")
```

### Example 3: Check Availability
```
"Is ISBN 978-0-262-03384-8 available?"
→ check_availability("978-0-262-03384-8")
```

### Example 4: Get Full Details
```
"Get details for ISBN 978-0-262-03384-8 from Library of Congress"
→ get_record_details("978-0-262-03384-8", "loc")
```

### Example 5: List Available Libraries
```
"What libraries are available?"
→ list_libraries()
```

### Example 6: Browse Subjects
```
"Show me history subjects in Library of Congress"
→ browse_subjects("loc", subject_prefix="History", limit=20)
```

### Example 7: Export MARC Record
```
"Export the MARC record for ISBN 978-0-262-03384-8"
→ export_marc_record("978-0-262-03384-8", "loc", format="binary")
```

## 5. Run Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run all tests
python -m pytest tests/ -v

# Run with timing
python -m pytest tests/ -v --tb=short
```

## 6. View Debug Output

Start server with debug logging:

```bash
python server.py --debug
```

This shows:
- Connection attempts and status
- Query construction and execution
- MARC record parsing details
- Performance metrics

## 7. Add Your Own Library

Edit `config/libraries.json`:

```json
{
  "my-library": {
    "name": "My Library System",
    "host": "z3950.mylib.edu",
    "port": 210,
    "database": "mylibdb",
    "preferred_syntax": "USMARC",
    "timeout": 5,
    "max_records": 100
  }
}
```

Then restart the server and it's available!

## 8. Performance Tips

- **Single library is fastest**: `check_availability("ISBN", libraries="loc")`
- **Binary MARC export is fastest**: `export_marc_record(..., format="binary")`
- **ISBN queries are fastest**: `search_libraries("ISBN", query_type="isbn")`
- **Results are cached for 5 minutes** by default

## 9. Troubleshooting

### "Connection timeout"
- Try specific library: `libraries="loc"` instead of all
- Check library is online via `list_libraries()`
- Increase timeout in config

### "No results found"
- Try different search type (author vs. title)
- Try broad keyword search first
- Check ISBN format (some need hyphens removed)

### "Import error: No module named 'fastmcp'"
```bash
pip install fastmcp
```

### "Record parsing failed"
- Some libraries return different MARC formats
- Try alternative library system
- Check library configuration in `config/libraries.json`

## 10. Next Steps

- Read [README.md](README.md) for comprehensive documentation
- Check [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) for architecture details
- Review [server.py](server.py) for available tools and examples
- Explore [config/libraries.json](config/libraries.json) to add more libraries

## Quick Reference

| Task | Command |
|------|---------|
| Start server | `python server.py` |
| Run tests | `pytest tests/ -v` |
| Debug mode | `python server.py --debug` |
| Search book | `search_libraries("title", query_type="title")` |
| Check availability | `check_availability("ISBN")` |
| Get details | `get_record_details("ISBN", "loc")` |
| Export MARC | `export_marc_record("ISBN", "loc")` |
| List libraries | `list_libraries()` |
| Browse subjects | `browse_subjects("loc", "History")` |

## Architecture Reminder

```
Fast Search Flow:
1. Query arrives at MCP server
2. QueryBuilder creates Z39.50 query (CCL format)
3. AsyncConnectionPool manages connections to multiple libraries
4. Queries execute in parallel (async/await)
5. Z39.50 returns MARC binary records
6. MARCProcessor extracts fields efficiently
7. Results deduplicated (O(1) via ISBN)
8. Results returned to client
```

Average time for multi-library search: **< 5 seconds**

## Support Resources

- **Z39.50 Protocol**: https://www.loc.gov/z3950/
- **MARC Format**: https://www.loc.gov/marc/
- **PyZ3950 Docs**: http://www.panix.com/~asl2/software/PyZ3950/
- **PyMARC Docs**: https://pymarc.readthedocs.io/
- **MCP Docs**: https://modelcontextprotocol.io/

Enjoy searching! 🔍📚
