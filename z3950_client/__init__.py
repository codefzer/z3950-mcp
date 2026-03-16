"""
Z39.50 MCP Client Integration Layer.
Provides async connection pooling, MARC processing, and query building.
"""

from .connection_pool import (
    AsyncConnectionPool,
    get_shared_pool,
    close_shared_pool,
    run_query_parallel,
)
from .record_processor import (
    MARCProcessor,
    MARCFields,
    get_shared_processor,
)
from .query import QueryBuilder, get_shared_query_builder

__all__ = [
    'AsyncConnectionPool',
    'get_shared_pool',
    'close_shared_pool',
    'run_query_parallel',
    'MARCProcessor',
    'MARCFields',
    'get_shared_processor',
    'QueryBuilder',
    'get_shared_query_builder',
]
