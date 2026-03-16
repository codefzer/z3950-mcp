"""
Browse tool for exploring library categories and subjects.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List, Union

from z3950_protocol import zoom
from z3950_client.connection_pool import get_shared_pool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Subject browsing
# ---------------------------------------------------------------------------

async def browse_subjects(
    library: str,
    subject_prefix: str = '',
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Browse available subjects/categories in a library using Z39.50 SCAN.

    Args:
        library: Library ID.
        subject_prefix: Starting prefix for scan.
        limit: Max terms to return.

    Returns:
        Dict with subjects list.
    """
    pool = await get_shared_pool()
    logger.info(f"Browsing subjects in {library} starting with '{subject_prefix}'")

    try:
        conn = await pool.get_connection(library)
        if not conn:
            return {'library': library, 'error': 'Connection failed'}

        result = await asyncio.to_thread(_scan_subjects, conn, subject_prefix, limit)
        result['library'] = library
        return result

    except Exception as e:
        logger.error(f"Error browsing subjects: {e}")
        return {'library': library, 'error': str(e)}


def _scan_subjects(conn, subject_prefix: str, limit: int) -> Dict[str, Any]:
    """Blocking scan on a single connection."""
    try:
        # Build a CCL scan query for subjects
        scan_query = zoom.Query('CCL', f'su="{subject_prefix}"')
        scanset = conn.scan(scan_query)

        subjects: List[Dict[str, Any]] = []
        count = min(len(scanset), limit) if scanset else 0
        for i in range(count):
            # Fix 4: robust ScanSet entry parsing; handle both dict and other types
            try:
                entry = scanset[i]
                term = ''
                freq: Any = 0
                if isinstance(entry, dict):
                    term = entry.get('term') or entry.get('display', '')
                    freq = entry.get('freq', entry.get('count', 0))
                else:
                    term = str(entry)
                if term:
                    subjects.append({'term': str(term), 'count': freq})
            except Exception:
                continue

        return {
            'prefix': subject_prefix,
            'subjects': subjects,
            'total': len(subjects),
        }

    except Exception as e:
        logger.warning(f"SCAN not fully supported: {e}")

        # Fallback: common subject headings
        common_subjects = [
            'Fiction', 'History', 'Biography', 'Science', 'Technology',
            'Medicine', 'Art', 'Music', 'Literature', 'Philosophy',
            'Psychology', 'Religion', 'Social Sciences', 'Business',
            'Education', 'Law', 'Sports', 'Travel', 'Cooking', 'Reference',
        ]
        filtered = [
            s for s in common_subjects
            if s.lower().startswith(subject_prefix.lower())
        ][:limit]

        return {
            'prefix': subject_prefix,
            'subjects': [{'term': s, 'count': 'Unknown'} for s in filtered],
            'total': len(filtered),
            'note': 'Using common subjects list (SCAN not supported)',
        }


# ---------------------------------------------------------------------------
# Library listing
# ---------------------------------------------------------------------------

async def browse_libraries() -> Dict[str, Any]:
    """Get list of available libraries and their metadata."""
    pool = await get_shared_pool()
    libraries: List[Dict[str, Any]] = []

    for lib_id in pool.list_libraries():
        config = pool.get_library_config(lib_id)
        if config:
            libraries.append({
                'id': lib_id,
                'name': config.get('name', lib_id),
                'description': config.get('description', ''),
                'host': config.get('host', ''),
                'port': config.get('port', 0),
            })

    return {'libraries': libraries, 'total': len(libraries)}


# ---------------------------------------------------------------------------
# FastMCP tool entry points
# ---------------------------------------------------------------------------

async def browse_tool(
    library: str, subject_prefix: str = '', limit: int = 20
) -> str:
    """MCP tool for browsing library subjects."""
    result = await browse_subjects(library, subject_prefix, limit)
    return json.dumps(result, indent=2)


async def browse_libraries_tool() -> str:
    """MCP tool for listing available libraries."""
    result = await browse_libraries()
    return json.dumps(result, indent=2)
