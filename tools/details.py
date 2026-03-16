"""
Details tool for retrieving full bibliographic record information.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional

from z3950_client.connection_pool import get_shared_pool
from z3950_client.record_processor import get_shared_processor
from z3950_client.query import QueryBuilder

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core detail retrieval
# ---------------------------------------------------------------------------

async def get_record_details(
    isbn: str,
    library: str,
) -> Dict[str, Any]:
    """
    Retrieve full bibliographic record for a specific ISBN from a library.

    Args:
        isbn: ISBN to retrieve.
        library: Library ID.

    Returns:
        Comprehensive record dict.
    """
    pool = await get_shared_pool()
    logger.info(f"Retrieving details for ISBN {isbn} from {library}")

    try:
        conn = await pool.get_connection(library)
        if not conn:
            return {'isbn': isbn, 'library': library, 'error': 'Connection failed'}

        result = await asyncio.to_thread(_fetch_details, conn, isbn)
        result['library'] = library
        return result

    except Exception as e:
        logger.error(f"Error retrieving details: {e}")
        return {'isbn': isbn, 'library': library, 'error': str(e)}


def _fetch_details(conn, isbn: str) -> Dict[str, Any]:
    """Blocking detail fetch on a single connection."""
    qbuilder = QueryBuilder()
    query = qbuilder.build_ccl_query('isbn', isbn)
    if not query:
        return {'isbn': isbn, 'found': False, 'error': 'Invalid query'}

    resultset = conn.search(query)
    hit_count = len(resultset)

    if hit_count == 0:
        return {'isbn': isbn, 'found': False, 'message': 'No records found'}

    processor = get_shared_processor()
    zoom_record = resultset[0]
    parsed = processor.parse_zoom_record(zoom_record)

    if not parsed:
        return {'isbn': isbn, 'found': False, 'error': 'Failed to parse MARC record'}

    rec_dict = processor.extract_full_fields(parsed)
    rec_dict['isbn'] = isbn
    rec_dict['found'] = True
    return rec_dict


# ---------------------------------------------------------------------------
# FastMCP tool entry point
# ---------------------------------------------------------------------------

async def details_tool(isbn: str, library: str) -> str:
    """MCP tool for retrieving full record details."""
    result = await get_record_details(isbn, library)
    return json.dumps(result, indent=2)
