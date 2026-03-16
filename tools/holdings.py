"""
Holdings/Availability tool for checking item status across libraries.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List

from pymarc import Record as PymarcRecord

from z3950_client.connection_pool import get_shared_pool
from z3950_client.record_processor import get_shared_processor, MARCFields, fetch_first_record_by_isbn

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

    # Parallelize both connection acquisition and blocking checks
    async def _check_one(lib_id: str) -> tuple:
        conn = await pool.get_connection(lib_id)
        if not conn:
            return lib_id, {'available': False, 'error': 'Connection failed'}
        result = await asyncio.to_thread(_check_single, conn, isbn)
        return lib_id, result

    results = await asyncio.gather(
        *[_check_one(lib_id) for lib_id in libraries],
        return_exceptions=True,
    )

    for item in results:
        if isinstance(item, Exception):
            logger.error(f"Error checking availability: {item}")
            continue
        lib_id, result = item
        availability['libraries'][lib_id] = result

    return availability


def _check_single(conn, isbn: str) -> Dict[str, Any]:
    """Blocking check on a single connection."""
    parsed, hit_count = fetch_first_record_by_isbn(conn, isbn)

    if hit_count == 0:
        return {'available': False, 'found': False}

    processor = get_shared_processor()

    if parsed:
        rec_dict = processor.extract_minimal_fields(parsed)
        rec_dict['available'] = True
        rec_dict['holdings'] = _extract_holdings(parsed)
        return rec_dict
    return {'available': True, 'found': True}


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
