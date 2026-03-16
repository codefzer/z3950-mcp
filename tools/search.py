"""
Search tool for Z39.50 library queries.
Implements parallel querying across multiple libraries for fast results.
"""

import json
import logging
from typing import List, Dict, Any, Optional

from z3950_client.connection_pool import get_shared_pool, run_query_parallel
from z3950_client.record_processor import get_shared_processor
from z3950_client.query import get_shared_query_builder

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core search (runs synchronously inside asyncio.to_thread via the pool)
# ---------------------------------------------------------------------------

def _search_single_library(
    conn,
    query: str,
    query_type: str,
    max_results: int,
) -> List[Dict[str, Any]]:
    """
    Execute search on a single Z39.50 connection (blocking).

    Args:
        conn: zoom.Connection object.
        query: Search value.
        query_type: title | author | isbn | subject | keyword ...
        max_results: Cap on records to retrieve.

    Returns:
        List of record dicts.
    """
    results: List[Dict[str, Any]] = []

    try:
        qbuilder = get_shared_query_builder()
        z_query = qbuilder.build_ccl_query(query_type, query)
        if not z_query:
            return results

        logger.debug(f"Executing query on {conn.databaseName}")

        # conn.search() returns a ResultSet, NOT an int
        resultset = conn.search(z_query)
        hit_count = len(resultset)

        if hit_count == 0:
            logger.info("No results found")
            return results

        logger.info(f"Found {hit_count} results, retrieving up to {max_results}")

        processor = get_shared_processor()
        num_to_fetch = min(hit_count, max_results)

        for i in range(num_to_fetch):
            try:
                zoom_record = resultset[i]          # zoom.Record object
                parsed = processor.parse_zoom_record(zoom_record)
                if parsed and processor.validate_record(parsed):
                    rec_dict = processor.extract_minimal_fields(parsed)
                    results.append(rec_dict)
            except Exception as e:
                logger.warning(f"Error retrieving record {i}: {e}")
                continue
    except Exception as e:
        logger.error(f"Search failed on {getattr(conn, 'databaseName', '?')}: {e}")
        return []

    logger.info(f"Retrieved {len(results)} records from {conn.databaseName}")
    return results


# ---------------------------------------------------------------------------
# High-level async search across libraries
# ---------------------------------------------------------------------------

async def search_libraries(
    query: str,
    libraries: List[str],
    query_type: str = 'keyword',
    max_results: int = 50,
    pool=None,
) -> Dict[str, Any]:
    """
    Search multiple libraries in parallel.

    Returns:
        Aggregated, deduplicated result dict.
    """
    if pool is None:
        pool = await get_shared_pool()
    logger.info(f"Searching {len(libraries)} libraries for {query_type}='{query}'")

    known_libraries = set(pool.list_libraries())
    query_tasks = []
    for lib_id in libraries:
        if lib_id not in known_libraries:
            logger.warning(f"Unknown library: {lib_id}")
            continue
        query_tasks.append(
            (lib_id, _search_single_library, (query, query_type, max_results), {})
        )

    results_list = await run_query_parallel(pool, query_tasks)

    all_results: List[Dict[str, Any]] = []
    errors: List[str] = []
    searched: List[str] = []

    for res in results_list:
        lib_id = res['library_id']
        if res.get('error'):
            errors.append(f"{lib_id}: {res['error']}")
        else:
            searched.append(lib_id)
        for rec in res.get('results', []):
            rec['library_id'] = lib_id
        all_results.extend(res.get('results', []))

    # Deduplicate
    processor = get_shared_processor()
    deduped = processor.deduplicate_records(all_results)

    # Sort: prefer records whose title starts with the query
    query_lower = query.lower()
    deduped.sort(
        key=lambda r: (
            r.get('title', '').lower().startswith(query_lower),
            r.get('title', '').lower().count(query_lower),
        ),
        reverse=True,
    )

    final = deduped[:max_results]

    return {
        'query': query,
        'query_type': query_type,
        'libraries_searched': searched,
        'total_results': len(final),
        'results': final,
        'errors': errors if errors else None,
        'deduplicated_from': len(all_results),
    }


# ---------------------------------------------------------------------------
# FastMCP tool entry point
# ---------------------------------------------------------------------------

async def search_tool(
    query: str,
    libraries: Optional[str] = None,
    query_type: str = 'keyword',
    max_results: int = 50,
) -> str:
    """MCP tool for searching library catalogs."""
    pool = await get_shared_pool()

    lib_list = (
        [lib.strip() for lib in libraries.split(',')]
        if libraries
        else pool.list_libraries()
    )

    result = await search_libraries(
        query=query,
        libraries=lib_list,
        query_type=query_type,
        max_results=max_results,
        pool=pool,
    )
    return json.dumps(result, indent=2)
