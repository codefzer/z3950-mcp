"""
Export tool for MARC record download in multiple formats.
Optimized for speed - prefers binary MARC format.
"""

import asyncio
import base64
import json
import logging
from typing import Dict, Any, Optional
from xml.sax.saxutils import escape as xml_escape

from pymarc import Record as PymarcRecord

from z3950_client.connection_pool import get_shared_pool
from z3950_client.record_processor import get_shared_processor, fetch_first_record_by_isbn

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core export
# ---------------------------------------------------------------------------

async def export_marc_record(
    isbn: str,
    library: str,
    export_format: str = 'binary',
) -> Dict[str, Any]:
    """
    Export MARC record in the requested format.

    Args:
        isbn: ISBN to export.
        library: Library ID.
        export_format: 'binary', 'json', or 'xml'.

    Returns:
        Dict with encoded MARC data and metadata.
    """
    pool = await get_shared_pool()
    logger.info(f"Exporting MARC for ISBN {isbn} from {library} as {export_format}")

    try:
        conn = await pool.get_connection(library)
        if not conn:
            return {'isbn': isbn, 'library': library, 'error': 'Connection failed'}

        result = await asyncio.to_thread(
            _fetch_and_export, conn, isbn, export_format
        )
        result['library'] = library
        return result

    except Exception as e:
        logger.error(f"Error exporting record: {e}")
        return {'isbn': isbn, 'library': library, 'error': str(e)}


def _fetch_and_export(conn, isbn: str, export_format: str) -> Dict[str, Any]:
    """Blocking fetch + format conversion."""
    parsed, hit_count = fetch_first_record_by_isbn(conn, isbn)

    if hit_count == 0:
        return {'isbn': isbn, 'found': False, 'message': 'No records found'}

    if not parsed:
        return {'isbn': isbn, 'error': 'Failed to parse MARC record'}

    title = 'Unknown'
    try:
        title = parsed.title if parsed.title else 'Unknown'
    except Exception:
        pass

    clean_isbn = isbn.replace('-', '').replace(' ', '').strip()
    export_data: Dict[str, Any] = {
        'isbn': isbn,
        'format': export_format,
        'found': True,
        'title': title,
    }

    processor = get_shared_processor()

    if export_format == 'binary':
        binary = processor.record_to_marc_binary(parsed)
        export_data['data'] = base64.b64encode(binary).decode('utf-8')
        export_data['size_bytes'] = len(binary)
        export_data['filename'] = f"{clean_isbn}.mrc"

    elif export_format == 'json':
        # detect silent failure (record_to_json returns "{}" on error)
        json_str = processor.record_to_json(parsed)
        try:
            parsed_json = json.loads(json_str)
        except json.JSONDecodeError:
            return {'isbn': isbn, 'error': 'Failed to serialize record as JSON'}
        if not parsed_json:
            return {'isbn': isbn, 'error': 'Failed to serialize record as JSON'}
        export_data['data'] = parsed_json
        export_data['filename'] = f"{clean_isbn}.json"

    elif export_format == 'xml':
        xml_str = _marc_to_xml(parsed)
        export_data['data'] = xml_str
        export_data['filename'] = f"{clean_isbn}.xml"

    else:
        return {'isbn': isbn, 'error': f'Unsupported format: {export_format}'}

    return export_data


# ---------------------------------------------------------------------------
# XML helper
# ---------------------------------------------------------------------------

def _marc_to_xml(record) -> str:
    """
    Convert PyMARC Record to MARC-XML string.
    All text values are entity-escaped to produce valid XML.
    """
    if not isinstance(record, PymarcRecord):
        return '<record/>'

    try:
        lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<record>']

        if record.leader:
            # Leader is structural data - escape for safety
            lines.append(f'  <leader>{xml_escape(str(record.leader))}</leader>')

        for field in record.fields:
            # Control fields are 001-009; string comparison is faster than int()
            if field.tag < '010':
                lines.append(
                    f'  <controlfield tag="{field.tag}">'
                    f'{xml_escape(field.value())}</controlfield>'
                )
            else:
                ind1 = getattr(field, 'indicator1', ' ')
                ind2 = getattr(field, 'indicator2', ' ')
                lines.append(
                    f'  <datafield tag="{field.tag}" '
                    f'ind1="{xml_escape(str(ind1))}" ind2="{xml_escape(str(ind2))}">'
                )
                if hasattr(field, 'subfields'):
                    try:
                        for sf in field:
                            lines.append(
                                f'    <subfield code="{xml_escape(str(sf.code))}">'
                                f'{xml_escape(str(sf.value))}</subfield>'
                            )
                    except Exception:
                        # Fallback for older PyMARC API
                        for idx in range(0, len(field.subfields), 2):
                            code = field.subfields[idx]
                            val = field.subfields[idx + 1]
                            lines.append(
                                f'    <subfield code="{xml_escape(str(code))}">'
                                f'{xml_escape(str(val))}</subfield>'
                            )
                lines.append('  </datafield>')

        lines.append('</record>')
        return '\n'.join(lines)

    except Exception as e:
        logger.error(f"Error converting to XML: {e}")
        return '<record/>'


# ---------------------------------------------------------------------------
# FastMCP tool entry point
# ---------------------------------------------------------------------------

async def export_tool(isbn: str, library: str, export_format: str = 'binary') -> str:
    """MCP tool for exporting MARC records."""
    result = await export_marc_record(isbn, library, export_format)
    return json.dumps(result, indent=2)
