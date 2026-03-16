"""
Async connection pool for Z39.50 servers.
Manages persistent connections for efficient multi-library queries.
Provides a singleton pool shared across all MCP tools.
"""

import asyncio
import json
import logging
from typing import Dict, Optional, Any, List, Callable, Tuple
from pathlib import Path

from z3950_protocol import zoom

logger = logging.getLogger(__name__)


class AsyncConnectionPool:
    """
    Manages persistent connections to multiple Z39.50 servers.
    Connections are cached and reused for fast repeated queries.
    """

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or str(
            Path(__file__).parent.parent / 'config' / 'libraries.json'
        )
        self.connections: Dict[str, zoom.Connection] = {}
        self.config: Dict[str, Any] = {}
        self.locks: Dict[str, asyncio.Lock] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load library configurations from JSON file and pre-initialize locks."""
        try:
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
            logger.info(f"Loaded {len(self.config)} library configurations")
        except FileNotFoundError:
            logger.warning(f"Config file not found: {self.config_path}")
            self.config = {}
        # Fix 5: pre-initialize all locks so they exist before any async code runs,
        # eliminating the lazy initialization race window.
        self.locks = {lib_id: asyncio.Lock() for lib_id in self.config}

    def _is_connection_alive(self, conn: zoom.Connection) -> bool:
        """Check if a connection is still active."""
        try:
            return (
                hasattr(conn, '_cli')
                and conn._cli is not None
                and hasattr(conn._cli, 'sock')
                and conn._cli.sock is not None
            )
        except Exception as e:
            # Fix 10: log the exception at debug level instead of silently swallowing
            logger.debug(f"Connection alive check failed: {e}")
            return False

    async def get_connection(
        self, library_id: str, institution_id: Optional[str] = None
    ) -> Optional[zoom.Connection]:
        """
        Get or create a connection to a library.
        Reuses existing connections from the pool when available.
        """
        if library_id not in self.config:
            logger.error(f"Unknown library: {library_id}")
            return None

        # Locks are pre-initialized in _load_config (Fix 5)
        async with self.locks[library_id]:
            # Return cached connection if alive
            if library_id in self.connections:
                conn = self.connections[library_id]
                if self._is_connection_alive(conn):
                    return conn
                else:
                    logger.warning(f"Connection to {library_id} dead, reconnecting")
                    try:
                        conn.close()
                    except Exception:
                        pass
                    del self.connections[library_id]

            # Create new connection (blocking I/O → run in thread)
            try:
                cfg = self.config[library_id]
                host = cfg['host']
                port = cfg['port']
                database = cfg['database']

                if institution_id and '{institution_id}' in database:
                    database = database.format(institution_id=institution_id)

                logger.info(f"Connecting to {library_id} ({host}:{port}/{database})")

                conn = await asyncio.to_thread(zoom.Connection, host, port)
                conn.databaseName = database
                conn.preferredRecordSyntax = cfg.get('preferred_syntax', 'USMARC')

                self.connections[library_id] = conn
                logger.info(f"Connected to {library_id}")
                return conn

            except Exception as e:
                logger.error(f"Failed to connect to {library_id}: {e}")
                return None

    async def close_all(self) -> None:
        """Close all connections in the pool."""
        for library_id, conn in list(self.connections.items()):
            try:
                conn.close()
                logger.info(f"Closed connection to {library_id}")
            except Exception as e:
                logger.warning(f"Error closing {library_id}: {e}")
        self.connections.clear()

    def get_library_config(self, library_id: str) -> Optional[Dict[str, Any]]:
        """Get library configuration."""
        return self.config.get(library_id)

    def list_libraries(self) -> List[str]:
        """List all configured library IDs."""
        return list(self.config.keys())

    async def test_connection(self, library_id: str) -> bool:
        """Test if a connection to library works."""
        try:
            conn = await self.get_connection(library_id)
            return conn is not None
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Singleton pool shared across all MCP tools
# ---------------------------------------------------------------------------

_shared_pool: Optional[AsyncConnectionPool] = None


async def get_shared_pool() -> AsyncConnectionPool:
    """Get or create the shared connection pool singleton."""
    global _shared_pool
    if _shared_pool is None:
        _shared_pool = AsyncConnectionPool()
    return _shared_pool


async def close_shared_pool() -> None:
    """Close the shared pool. Called on server shutdown."""
    global _shared_pool
    if _shared_pool is not None:
        await _shared_pool.close_all()
        _shared_pool = None


# ---------------------------------------------------------------------------
# Parallel query execution
# ---------------------------------------------------------------------------

async def run_query_parallel(
    pool: AsyncConnectionPool,
    query_tasks: List[Tuple[str, Callable, tuple, dict]],
) -> List[Dict[str, Any]]:
    """
    Run multiple queries in parallel across different libraries.

    Args:
        pool: AsyncConnectionPool instance
        query_tasks: List of (library_id, query_func, args, kwargs) tuples

    Returns:
        List of result dicts with keys: library_id, error, results
    """
    tasks = [
        _run_single_query(pool, library_id, query_func, args, kwargs)
        for library_id, query_func, args, kwargs in query_tasks
    ]
    return await asyncio.gather(*tasks, return_exceptions=False)


async def _run_single_query(
    pool: AsyncConnectionPool,
    library_id: str,
    query_func: Callable,
    args: tuple,
    kwargs: dict,
) -> Dict[str, Any]:
    """Run a single query. Blocking Z39.50 calls are wrapped with to_thread."""
    try:
        conn = await pool.get_connection(library_id)
        if not conn:
            return {'library_id': library_id, 'error': 'Connection failed', 'results': []}

        result = await asyncio.to_thread(query_func, conn, *args, **kwargs)
        return {'library_id': library_id, 'error': None, 'results': result}
    except asyncio.TimeoutError:
        return {'library_id': library_id, 'error': 'Timeout', 'results': []}
    except Exception as e:
        logger.error(f"Query failed for {library_id}: {e}")
        return {'library_id': library_id, 'error': str(e), 'results': []}
