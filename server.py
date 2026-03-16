#!/usr/bin/env python3
"""
Z39.50 Library System MCP Server
Provides fast, efficient library search across multiple Z39.50 systems.
"""

import asyncio
import logging
from typing import Optional

from fastmcp import FastMCP

# Import tools
from tools.search import search_tool
from tools.holdings import holdings_tool
from tools.details import details_tool
from tools.browse import browse_tool, browse_libraries_tool
from tools.export import export_tool

# Import resources
from resources.library_info import get_library_resource

# Import pool lifecycle
from z3950_client.connection_pool import close_shared_pool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Create MCP server
server = FastMCP("Z39.50-Library-Search")


# ============================================================================
# Tools
# ============================================================================

@server.tool()
async def search_libraries(
    query: str,
    libraries: Optional[str] = None,
    query_type: str = 'keyword',
    max_results: int = 50,
) -> str:
    """
    Search multiple library systems in parallel.

    Use this tool to search for books across different library catalogs
    (Library of Congress, OCLC WorldCat, academic library networks, etc.).

    Args:
        query: What to search for (book title, author name, ISBN, etc.)
        libraries: Comma-separated library IDs (defaults to all available)
                   Available: loc, worldcat, i-share
        query_type: Type of search - 'title', 'author', 'isbn', 'subject', 'keyword'
        max_results: Maximum number of results per library (default: 50)

    Returns:
        JSON with search results, including title, author, ISBN, publisher

    Examples:
        search_libraries("Hamlet", query_type="title")
        search_libraries("Shakespeare", libraries="loc,worldcat", query_type="author")
        search_libraries("978-0-262-03384-8", query_type="isbn")
    """
    logger.info(f"Searching for: {query_type}='{query}' across {libraries or 'all'}")
    return await search_tool(query, libraries, query_type, max_results)


@server.tool()
async def check_availability(isbn: str, libraries: Optional[str] = None) -> str:
    """
    Check if a book is available across multiple libraries.

    Args:
        isbn: ISBN of the book to check
        libraries: Comma-separated library IDs (defaults to all)

    Returns:
        JSON with availability information from each library

    Examples:
        check_availability("978-0-262-03384-8")
        check_availability("0-13-110362-8", libraries="loc,worldcat")
    """
    logger.info(f"Checking availability for ISBN: {isbn}")
    return await holdings_tool(isbn, libraries)


@server.tool()
async def get_record_details(isbn: str, library: str) -> str:
    """
    Get complete bibliographic details for a specific book from a library.

    Args:
        isbn: ISBN of the book
        library: Library ID to retrieve from (e.g., 'loc', 'worldcat')

    Returns:
        JSON with detailed bibliographic record

    Examples:
        get_record_details("978-0-262-03384-8", "loc")
        get_record_details("0-13-110362-8", "worldcat")
    """
    logger.info(f"Getting details for ISBN {isbn} from {library}")
    return await details_tool(isbn, library)


@server.tool()
async def browse_subjects(
    library: str, subject_prefix: str = '', limit: int = 20
) -> str:
    """
    Browse available subjects/categories in a library.

    Args:
        library: Library ID (e.g., 'loc', 'worldcat')
        subject_prefix: Optional subject prefix
        limit: Maximum subjects to return (default: 20)

    Returns:
        JSON with list of available subjects

    Examples:
        browse_subjects("loc")
        browse_subjects("worldcat", subject_prefix="History")
    """
    logger.info(f"Browsing subjects in {library}")
    return await browse_tool(library, subject_prefix, limit)


@server.tool()
async def list_libraries() -> str:
    """
    List all available library systems.

    Returns:
        JSON with list of configured libraries
    """
    logger.info("Listing available libraries")
    return await browse_libraries_tool()


@server.tool()
async def export_marc_record(
    isbn: str, library: str, export_format: str = 'binary'
) -> str:
    """
    Export a MARC bibliographic record in multiple formats.

    Args:
        isbn: ISBN of the book to export
        library: Library ID to export from
        export_format: 'binary' (fast), 'json', or 'xml'

    Returns:
        JSON with encoded MARC record data

    Examples:
        export_marc_record("978-0-262-03384-8", "loc", export_format="binary")
        export_marc_record("0-13-110362-8", "worldcat", export_format="json")
    """
    logger.info(f"Exporting MARC record for ISBN {isbn} as {export_format}")
    return await export_tool(isbn, library, export_format)


# ============================================================================
# Resources
# ============================================================================

@server.resource("library://all")
def get_all_libraries() -> str:
    """Get information about all configured libraries."""
    return get_library_resource('all') or '{"libraries": []}'


@server.resource("library://{library_id}")
def get_library_details(library_id: str) -> str:
    """Get detailed information about a specific library."""
    return get_library_resource(library_id) or '{"error": "Library not found"}'


@server.resource("help://search-syntax")
def get_search_help() -> str:
    """Get help about search syntax and available search types."""
    return get_library_resource('search-help') or "No help available"


# ============================================================================
# Startup and shutdown
# ============================================================================

async def initialize():
    """Initialize server resources."""
    logger.info("Z39.50 MCP Server starting...")
    logger.info("Available libraries: loc, worldcat, i-share")
    logger.info(
        "Tools: search_libraries, check_availability, get_record_details, "
        "browse_subjects, list_libraries, export_marc_record"
    )


async def cleanup():
    """Clean up resources on shutdown."""
    logger.info("Z39.50 MCP Server shutting down...")
    await close_shared_pool()
    logger.info("Connection pool closed")


if __name__ == "__main__":
    import sys

    if '--debug' in sys.argv:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")

    try:
        asyncio.run(initialize())
        server.run()
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    except Exception as e:
        # Fix 11: log unexpected errors before cleanup so they appear in the log
        logger.error(f"Server error: {e}", exc_info=True)
    finally:
        asyncio.run(cleanup())
