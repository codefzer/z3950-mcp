# Z39.50 Library System MCP Server

Fast, efficient MCP (Model Context Protocol) server for searching library catalogs across multiple Z39.50-enabled library systems.

## Features

- **Fast Parallel Search**: Query multiple libraries simultaneously using async I/O
- **Multiple Library Systems**: Library of Congress, OCLC WorldCat, academic library networks
- **Rich Search Options**: Title, author, ISBN, subject, keyword searches
- **Availability Checking**: Find which libraries have specific books
- **Detailed Records**: Retrieve comprehensive bibliographic information
- **MARC Export**: Download records in binary MARC, JSON, or XML formats
- **Result Deduplication**: Intelligent merging of results across libraries
- **Connection Pooling**: Persistent connections for optimal performance

## Quick Start

### Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

### Running the Server

```bash
# Start the MCP server
python server.py

# With debug logging
python server.py --debug
```

### Using with Claude Desktop

Add to your Claude Desktop configuration:

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

Then restart Claude Desktop and the Z39.50 tools will be available.

## Available Tools

### search_libraries
Search across multiple library systems.

```
search_libraries(
  query: "Harry Potter",
  libraries: "loc,worldcat",        # Optional: defaults to all
  query_type: "title",              # title, author, isbn, subject, keyword
  max_results: 50
)
```

**Examples:**
- Find books by title: `search_libraries("The Great Gatsby", query_type="title")`
- Find books by author: `search_libraries("Stephen King", query_type="author")`
- Find by ISBN: `search_libraries("978-0-262-03384-8", query_type="isbn")`

### check_availability
Check which libraries have a book in stock.

```
check_availability(
  isbn: "978-0-262-03384-8",
  libraries: "loc,worldcat"         # Optional: defaults to all
)
```

Returns availability status and call numbers for each library.

### get_record_details
Get comprehensive bibliographic information.

```
get_record_details(
  isbn: "978-0-262-03384-8",
  library: "loc"
)
```

Returns detailed metadata including author, publisher, subjects, publication year, etc.

### browse_subjects
Browse available subject categories.

```
browse_subjects(
  library: "loc",
  subject_prefix: "History",
  limit: 20
)
```

### list_libraries
Get information about available library systems.

```
list_libraries()
```

### export_marc_record
Download MARC records for local use.

```
export_marc_record(
  isbn: "978-0-262-03384-8",
  library: "loc",
  format: "binary"                  # binary, json, or xml
)
```

## Available Libraries

### Library of Congress (loc)
- **Host**: z3950.loc.gov:7090
- **Database**: Voyager
- **Description**: The largest library in the world with comprehensive collection

### OCLC WorldCat (worldcat)
- **Host**: z3950.oclc.org:210
- **Database**: WorldCat
- **Description**: The world's largest library catalog with records from thousands of libraries

### I-Share Consortium (i-share)
- **Host**: vufind.carli.illinois.edu:210
- **Database**: i-share
- **Description**: Illinois academic library network with content from major universities

### Ex Libris Alma (alma-template)
- **Host**: z3950.alma.exlibrisgroup.com:1921
- **Description**: Modern library management system (requires institution_id configuration)

## Configuration

Library configurations are in `config/libraries.json`. To add a new library:

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

## Performance Optimizations

The server is optimized for speed:

1. **Async Parallel Queries**: Multiple libraries queried simultaneously
2. **Connection Pooling**: Persistent connections eliminate handshake overhead
3. **Smart Timeouts**: 5-second timeout for fast failure on slow servers
4. **Binary MARC**: Preferred format (faster than JSON/XML)
5. **Lazy Parsing**: Only extract needed fields by default
6. **Result Deduplication**: O(1) duplicate detection via ISBN/control number
7. **Streaming Results**: Incremental result delivery

**Performance Targets:**
- Single library search: < 2 seconds
- Multi-library parallel search: < 5 seconds
- Cache hits: < 100ms

## Architecture

### Extracted PyZ3950 Modules (`z3950_protocol/`)
Core Z39.50 protocol implementation extracted from PyZ3950:
- `asn1.py`: ASN.1 BER encoder/decoder
- `zoom.py`: ZOOM API wrapper for high-level queries
- `z3950.py`: Core protocol implementation
- `pqf.py`: Prefix Query Format parser
- `zmarc.py`: MARC record parsing

### MCP Integration Layer (`z3950_client/`)
Custom wrappers for efficient MCP integration:
- `connection_pool.py`: Async connection management
- `record_processor.py`: Fast MARC record extraction
- `query.py`: Query building and validation

### MCP Tools (`tools/`)
FastMCP tool implementations:
- `search.py`: Parallel multi-library search
- `holdings.py`: Availability checking
- `details.py`: Full record retrieval
- `browse.py`: Subject browsing
- `export.py`: MARC record export

## Dependencies

- **fastmcp** (>=0.1.0): MCP server framework
- **pymarc** (>=5.0.0): MARC record processing
- **ply** (>=3.11): Query parser (PLY - Python Lex-Yacc)

All Z39.50 protocol implementation is pure Python with no compiled dependencies.

## Search Syntax

### CCL (Common Command Language)
The system uses CCL for intuitive searches:

- **Title**: `title="The Great Gatsby"`
- **Author**: `author="F. Scott Fitzgerald"`
- **ISBN**: `isbn="978-0-7432-7356-5"`
- **Subject**: `subject="American fiction"`
- **Keyword**: `keyword="gatsby"`
- **Publisher**: `publisher="Scribner"`
- **Year**: `year="1925"`

### Multiple Conditions
Combine with AND/OR:
- `author="Shakespeare" AND title="Hamlet"`
- `subject="History" OR subject="Biography"`

## Development

### Running Tests

```bash
# All tests
python -m pytest tests/ -v

# With performance benchmarks
python -m pytest tests/ -v --benchmark

# Specific test file
python -m pytest tests/test_search.py -v
```

### Adding New Libraries

1. Edit `config/libraries.json`
2. Test connection: `python -c "from z3950_client.connection_pool import AsyncConnectionPool; pool = AsyncConnectionPool(); print(asyncio.run(pool.test_connection('my-lib')))"`
3. Restart server

### Debug Mode

Run with debug logging:
```bash
python server.py --debug
```

## Troubleshooting

### Connection Timeout
- Check library is online: `list_libraries()` to verify configuration
- Increase timeout in `config/libraries.json`
- Try specific library instead of all

### No Results Found
- Try different search type (title vs. keyword)
- Check ISBN format (may need hyphens removed)
- Some libraries have limited collections

### MARC Parse Errors
- Ensure library returns USMARC format
- Try different query to get different records
- Contact library support for format configuration

## References

- [Z39.50 Protocol Overview](https://en.wikipedia.org/wiki/Z39.50)
- [MARC Records Guide](https://www.loc.gov/marc/)
- [PyZ3950 Documentation](http://www.panix.com/~asl2/software/PyZ3950/)
- [PyMARC Documentation](https://pymarc.readthedocs.io/)
- [MCP Documentation](https://modelcontextprotocol.io/)

## License

This project contains extracted code from PyZ3950 which is open source. See individual file headers for attribution.

## Contributing

To add new features or fix bugs:

1. Create a test case
2. Implement the feature
3. Ensure all tests pass
4. Update documentation

## Support

For issues with:
- **Z39.50 protocol**: Check [PyZ3950 docs](http://www.panix.com/~asl2/software/PyZ3950/)
- **MARC format**: See [Library of Congress MARC guide](https://www.loc.gov/marc/)
- **MCP integration**: Refer to [MCP documentation](https://modelcontextprotocol.io/)
