"""
Query building and translation for Z39.50 searches.
Supports CCL and PQF query formats with library system field mapping.
"""

import logging
from typing import Dict, Optional, List, Any

from z3950_protocol import zoom

logger = logging.getLogger(__name__)


class QueryBuilder:
    """
    Builds Z39.50 queries in multiple formats (CCL, PQF).
    Handles field mapping, escaping, and validation.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize query builder.

        Args:
            config: Optional library config dict with search_attributes.
        """
        self.config = config or {}
        self.search_attributes = self.config.get('search_attributes', {})

    # ------------------------------------------------------------------
    # Escaping
    # ------------------------------------------------------------------

    @staticmethod
    def escape_query_value(value: str) -> str:
        """
        Sanitize a query value for CCL embedding.
        Removes double-quotes since CCL values are wrapped in quotes by the
        query builder, and the PLY-based CCL lexer does not support escaped
        quotes inside quoted strings. Backslashes are also removed.
        """
        return value.replace('\\', '').replace('"', '')

    # ------------------------------------------------------------------
    # CCL Queries
    # ------------------------------------------------------------------

    # Mapping from our query types to CCL qualifiers.
    _CCL_QUALIFIERS = {
        'title': 'ti',
        'author': 'au',
        'isbn': 'nb',
        'issn': 'sn',
        'subject': 'su',
        'keyword': 'kw',
        'publisher': 'pb',
        'year': 'py',
    }

    def build_ccl_query(self, query_type: str, query_value: str) -> Optional[zoom.Query]:
        """
        Build a CCL query with proper escaping.

        Args:
            query_type: Search type (title, author, isbn, subject, keyword, …).
            query_value: Raw search value (will be escaped).

        Returns:
            zoom.Query or None on error.
        """
        try:
            escaped = self.escape_query_value(query_value)
            qualifier = self._CCL_QUALIFIERS.get(query_type, 'kw')
            ccl_str = f'{qualifier}="{escaped}"'
            logger.debug(f"CCL query: {ccl_str}")
            return zoom.Query('CCL', ccl_str)
        except Exception as e:
            logger.error(f"Failed to build CCL query: {e}")
            return None

    def build_combined_query(
        self, queries: List[Dict[str, str]], operator: str = 'and'
    ) -> Optional[zoom.Query]:
        """
        Build combined CCL query with AND/OR.

        Args:
            queries: List of {'type': …, 'value': …} dicts.
            operator: 'and' or 'or'.

        Returns:
            zoom.Query or None.
        """
        try:
            if not queries:
                return None

            parts = []
            for q in queries:
                qtype = q.get('type', 'keyword')
                qval = self.escape_query_value(q.get('value', ''))
                qualifier = self._CCL_QUALIFIERS.get(qtype, 'kw')
                parts.append(f'{qualifier}="{qval}"')

            ccl_str = f' {operator} '.join(parts)
            logger.debug(f"Combined CCL query: {ccl_str}")
            return zoom.Query('CCL', ccl_str)
        except Exception as e:
            logger.error(f"Failed to build combined query: {e}")
            return None

    # ------------------------------------------------------------------
    # PQF Queries (utility, for advanced use)
    # ------------------------------------------------------------------

    _PQF_ATTR_MAP = {
        'title': '4',
        'author': '1003',
        'isbn': '7',
        'issn': '8',
        'subject': '21',
        'keyword': '1016',
    }

    def build_pqf_query(self, query_type: str, query_value: str) -> Optional[zoom.Query]:
        """
        Build PQF query for precise attribute-based searches.

        Args:
            query_type: Search type.
            query_value: Raw search value (will be escaped).

        Returns:
            zoom.Query or None.
        """
        try:
            escaped = self.escape_query_value(query_value)
            attr_id = self.search_attributes.get(
                query_type, self._PQF_ATTR_MAP.get(query_type, '4')
            )
            rpn = f'@attr 1={attr_id} "{escaped}"'
            logger.debug(f"PQF query: {rpn}")
            return zoom.Query('PQF', rpn)
        except Exception as e:
            logger.error(f"Failed to build PQF query: {e}")
            return None

    # ------------------------------------------------------------------
    # ISBN validation
    # ------------------------------------------------------------------

    @staticmethod
    def validate_isbn(isbn: str) -> bool:
        """Basic ISBN-10/ISBN-13 format validation."""
        clean = isbn.replace('-', '').replace(' ', '').strip()
        if len(clean) == 10:
            return clean[:-1].isdigit() and (clean[-1].isdigit() or clean[-1].upper() == 'X')
        if len(clean) == 13:
            return clean.isdigit()
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def parse_search_syntax(search_string: str) -> Dict[str, str]:
        """
        Parse 'field:value field:value' style search strings.

        Returns:
            Dictionary of {field: value} pairs.
        """
        params: Dict[str, str] = {}
        for part in search_string.split():
            if ':' in part:
                field, value = part.split(':', 1)
                params[field.lower()] = value
            else:
                if 'keyword' not in params:
                    params['keyword'] = part
                else:
                    params['keyword'] += ' ' + part
        return params
