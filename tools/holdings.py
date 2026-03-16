"""
Holdings/Availability tool for checking item status across libraries.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List

from pymarc import Record as PymarcRecord

from z3950_client.connection_pool import get_shared_pool
from z3950_client.record_processor import get_shared_processor, MARCFields
from z3950_client.query import QueryBuilder

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core availability check
# ---------------------------------------------------------------------------

async def check_availability(
    isbn: str,
    libraries: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Check availability of a book across multiple libraries.

    Args:
        isbn: ISBN to check.
        libraries: Library IDs to check (defaults to all).

    Returns:
        Dict with per-library availability info.
    """
    pool = await get_shared_pool()

    if not libraries:
        libraries = pool.list_libraries()

    logger.info(f"Checking availability for ISBN: {isbn}")

    availability: Dict[str, Any] = {'isbn': isbn, 'libraries': {}}

    # Fix 2: resolve connections first (must be sequential - event loop only),
    # then dispatch all blocking checks in parallel with asyncio.gather.
    lib_tasks: List[tuple] = []  # (lib_id, coroutine)

    for lib_id in libraries:
        conn = await pool.get_connection(lib_id)
        if not conn:
            availability['libraries'][lib_id] = {
                'available': False,
                'error': 'Connection failed',
            }
        else:
            lib_tasks.append((lib_id, asyncio.to_thread(_check_single, conn, isbn)))

    if lib_tasks:
        results = await asyncio.gather(
            *[task for _, task in lib_tasks], return_exceptions=True
        )
        for (lib_id, _), result in zip(lib_tasks, results):
            if isinstance(result, Exception):
                logger.error(f"Error checking availability at {lib_id}: {result}")
                availability['libraries'][lib_id] = {
                    'available': False,
                    'error': str(result),
                }
            else:
                availability['libraries'][lib_id] = result

    return availability


def _check_single(conn, isbn: str) -> Dict[str, Any]:
    """Blocking check on a single connection."""
    qbuilder = QueryBuilder()
    query = qbuilder.build_ccl_query('isbn', isbn)
    if not query:
        return {'available': False, 'error': 'Invalid query'}

    resultset = conn.search(query)
    hit_count = len(resultset)

    if hit_count == 0:
        return {'available': False, 'found': False}

    processor = get_shared_processor()

    try:
        zoom_record = resultset[0]
        parsed = processor.parse_zoom_record(zoom_record)
        if parsed:
            rec_dict = processor.extract_minimal_fields(parsed)
            rec_dict['available'] = True
            rec_dict['holdings'] = _extract_holdings(parsed)
            return rec_dict
        return {'available': True, 'found': True}
    except Exception as e:
        return {'available': True, 'found': True, 'error_retrieving_details': str(e)}


# ---------------------------------------------------------------------------
# Holdings extraction from MARC 852
# ---------------------------------------------------------------------------

def _extract_holdings(record) -> Dict[str, Any]:
    """Extract holdings information from MARC 852 fields."""
    holdings: Dict[str, Any] = {}

    if not isinstance(record, PymarcRecord):
        return holdings

    try:
        for field in record.get_fields(MARCFields.HOLDINGS):
            subs_a = field.get_subfields('a')
            location = subs_a[0] if subs_a else 'Unknown'
            subs_h = field.get_subfields('h')
            call_number = subs_h[0] if subs_h else ''
            subs_i = field.get_subfields('i')
            if call_number and subs_i:
                call_number += ' ' + subs_i[0]

            holdings[location] = {
                'call_number': call_number.strip(),
                'location': location,
            }
    except Exception as e:
        logger.error(f"Error extracting holdings: {e}")

    return holdings


# ---------------------------------------------------------------------------
# FastMCP tool entry point
# ---------------------------------------------------------------------------

async def holdings_tool(isbn: str, libraries: Optional[str] = None) -> str:
    """MCP tool for checking book availability."""
    lib_list = (
        [lib.strip() for lib in libraries.split(',')]
        if libraries
        else None
    )
    result = await check_availability(isbn, lib_list)
    return json.dumps(result, indent=2)
