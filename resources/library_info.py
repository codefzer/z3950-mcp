"""
Library information resources for MCP
Provides metadata about configured library systems
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def get_library_info(library_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get library information and search documentation.

    Args:
        library_id: Library ID (all libraries if not specified)

    Returns:
        Dictionary with library information
    """
    config_path = Path(__file__).parent.parent / 'config' / 'libraries.json'

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        logger.warning(f"Config file not found: {config_path}")
        return {}

    if library_id:
        if library_id not in config:
            return {'error': f'Unknown library: {library_id}'}

        lib_config = config[library_id]
        return {
            'id': library_id,
            'name': lib_config.get('name', ''),
            'description': lib_config.get('description', ''),
            'host': lib_config.get('host', ''),
            'port': lib_config.get('port', 0),
            'database': lib_config.get('database', ''),
            'preferred_syntax': lib_config.get('preferred_syntax', 'USMARC'),
            'timeout': lib_config.get('timeout', 5),
            'max_records': lib_config.get('max_records', 100),
            'search_help': _get_search_help(lib_config),
            'available_searches': _get_available_searches()
        }

    else:
        # Return info for all libraries
        libraries = []
        for lib_id, lib_config in config.items():
            libraries.append({
                'id': lib_id,
                'name': lib_config.get('name', ''),
                'description': lib_config.get('description', '')
            })

        return {
            'libraries': libraries,
            'total': len(libraries),
            'available_searches': _get_available_searches()
        }


def _get_search_help(lib_config: Dict[str, Any]) -> str:
    """
    Get search syntax help for a library.

    Args:
        lib_config: Library configuration

    Returns:
        Help text with search examples
    """
    search_help = f"""
Library: {lib_config.get('name', 'Unknown')}
Host: {lib_config.get('host', 'Unknown')}:{lib_config.get('port', 'Unknown')}
Database: {lib_config.get('database', 'Unknown')}

Search Syntax (CCL - Common Command Language):
  Title search:    title="{lib_config.get('name', 'The Great Gatsby')}"
  Author search:   author="Shakespeare"
  ISBN search:     isbn="978-0-13-468599-1"
  Subject search:  subject="History"
  Keyword search:  keyword="Python programming"

Examples:
  search_libraries("Romeo and Juliet", libraries="loc", query_type="title")
  search_libraries("Stephen King", libraries="worldcat", query_type="author")
  check_availability("978-0-262-03384-8", libraries="loc,worldcat")
"""
    return search_help.strip()


def _get_available_searches() -> Dict[str, str]:
    """
    Get available search types.

    Returns:
        Dictionary describing available search types
    """
    return {
        'keyword': 'Free-text keyword search across all fields',
        'title': 'Search by book title',
        'author': 'Search by author name',
        'isbn': 'Search by ISBN (International Standard Book Number)',
        'issn': 'Search by ISSN (for periodicals)',
        'subject': 'Search by subject heading/category',
        'publisher': 'Search by publisher name',
        'year': 'Search by publication year'
    }


# Resource definitions for MCP
def get_library_resource(resource_id: str) -> Optional[str]:
    """
    Get resource content for MCP resource URI.

    Args:
        resource_id: Resource identifier (e.g., "loc", "all", "search-help")

    Returns:
        Resource content as string or None
    """
    if resource_id == 'all':
        info = get_library_info()
        return json.dumps(info, indent=2)

    elif resource_id == 'search-help':
        help_text = """
Z39.50 Library Search - User Guide

Supported Query Types:
  - keyword: Search across all fields
  - title: Book title
  - author: Author name
  - isbn: ISBN number
  - subject: Subject heading

Examples:

1. Search for a book by title across all libraries:
   search_libraries("Hamlet", query_type="title")

2. Search for books by a specific author:
   search_libraries("Jane Austen", libraries="loc", query_type="author")

3. Check availability by ISBN:
   check_availability("978-0-262-03384-8", libraries="worldcat")

4. Get detailed record information:
   get_record_details("978-0-262-03384-8", library="loc")

5. Export MARC record in binary format:
   export_marc_record("978-0-262-03384-8", library="loc", format="binary")

Available Libraries:
  - loc: Library of Congress
  - worldcat: OCLC WorldCat
  - i-share: Illinois academic library network
  - alma-template: Ex Libris Alma (requires institution_id)
"""
        return help_text.strip()

    else:
        # Specific library
        info = get_library_info(resource_id)
        if 'error' not in info:
            return json.dumps(info, indent=2)

    return None
