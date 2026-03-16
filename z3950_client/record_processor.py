"""
MARC Record Processing for efficient field extraction and normalization.
Uses PyMARC for validation and incremental parsing.
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from io import BytesIO

from pymarc import Record, MARCReader

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MARC field tag constants
# ---------------------------------------------------------------------------

class MARCFields:
    """Standard MARC 21 field tag constants."""
    CONTROL_NUMBER = '001'
    FIXED_LENGTH = '008'
    ISBN = '020'
    ISSN = '022'
    TITLE = '245'
    EDITION = '250'
    PUBLICATION = '260'
    PUBLICATION_RDA = '264'
    PHYSICAL_DESC = '300'
    SUBJECT = '650'
    AUTHOR = '100'
    AUTHOR_ADDED = '700'
    HOLDINGS = '852'


# ---------------------------------------------------------------------------
# MARCProcessor
# ---------------------------------------------------------------------------

class MARCProcessor:
    """
    Processes MARC records from Z39.50 servers with optimizations for speed.

    - Incremental parsing: extract only required fields
    - Lazy field expansion: full record details on demand
    - Multiple format support: binary MARC, JSON, XML
    """

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def parse_binary_marc(self, marc_data: bytes) -> Optional[Record]:
        """Parse binary MARC data into a PyMARC Record."""
        try:
            if not marc_data:
                return None
            reader = MARCReader(BytesIO(marc_data), to_unicode=True)
            return next(iter(reader), None)
        except Exception as e:
            logger.error(f"Failed to parse MARC data: {e}")
            return None

    def parse_zoom_record(self, zoom_record) -> Optional[Record]:
        """
        Parse a zoom.Record object (from a ResultSet) into a PyMARC Record.

        Args:
            zoom_record: A zoom.Record with a .data attribute containing raw bytes.

        Returns:
            PyMARC Record or None.
        """
        if zoom_record is None:
            return None
        try:
            raw_data = zoom_record.data
            if isinstance(raw_data, str):
                raw_data = raw_data.encode('latin-1')
                return self.parse_binary_marc(raw_data)
            elif isinstance(raw_data, bytes):
                return self.parse_binary_marc(raw_data)
            else:
                logger.warning(
                    f"Unsupported record syntax: {getattr(zoom_record, 'syntax', 'unknown')}"
                )
        except Exception as e:
            logger.error(f"Failed to parse zoom record: {e}")
        return None

    # ------------------------------------------------------------------
    # Field extraction
    # ------------------------------------------------------------------

    def _safe_subfield(self, field, code: str) -> Optional[str]:
        """Safely extract the first value of a subfield code."""
        try:
            vals = field.get_subfields(code)
            return vals[0] if vals else None
        except Exception as e:
            logger.debug(f"Could not read subfield {code}: {e}")
            return None

    def extract_minimal_fields(self, record: Record) -> Dict[str, Any]:
        """Extract minimal bibliographic fields for fast results."""
        if not record:
            return {}

        data: Dict[str, Any] = {}

        # Title (PyMARC 5.x: .title is a property, not a method)
        try:
            title = record.title
            if title:
                data['title'] = title.strip()
        except Exception as e:
            logger.debug(f"Could not extract title: {e}")

        # Author (PyMARC 5.x: .author is a property, not a method)
        try:
            author = record.author
            if author:
                data['author'] = author.strip()
        except Exception as e:
            logger.debug(f"Could not extract author: {e}")

        # ISBN
        try:
            isbns = []
            for field in record.get_fields(MARCFields.ISBN):
                isbn = self._safe_subfield(field, 'a')
                if isbn:
                    clean = isbn.replace('-', '').replace(' ', '').strip()
                    isbns.append(clean)
            if isbns:
                data['isbn'] = isbns[0] if len(isbns) == 1 else isbns
        except Exception as e:
            logger.debug(f"Could not extract ISBN: {e}")

        # Publisher and publication year (single pass over 260 fields)
        try:
            for field in record.get_fields(MARCFields.PUBLICATION):
                if 'publisher' not in data:
                    pub = self._safe_subfield(field, 'b')
                    if pub:
                        data['publisher'] = pub.strip().rstrip(',')
                if 'publication_year' not in data:
                    year_raw = self._safe_subfield(field, 'c')
                    if year_raw:
                        digits = ''.join(c for c in year_raw if c.isdigit())
                        if len(digits) >= 4:
                            data['publication_year'] = digits[:4]
                if 'publisher' in data and 'publication_year' in data:
                    break
        except Exception as e:
            logger.debug(f"Could not extract publisher/year: {e}")

        # Control Number
        try:
            ctrl = record[MARCFields.CONTROL_NUMBER]
            if ctrl:
                data['control_number'] = ctrl.value().strip()
        except Exception as e:
            logger.debug(f"Could not extract control number: {e}")

        return data

    def extract_full_fields(self, record: Record) -> Dict[str, Any]:
        """Extract comprehensive bibliographic fields."""
        data = self.extract_minimal_fields(record)
        if not record:
            return data

        # Subjects
        try:
            subjects = []
            for field in record.get_fields(MARCFields.SUBJECT):
                subj = self._safe_subfield(field, 'a')
                if subj:
                    subjects.append(subj.strip())
            if subjects:
                data['subjects'] = subjects
        except Exception as e:
            logger.debug(f"Could not extract subjects: {e}")

        # Edition
        try:
            for field in record.get_fields(MARCFields.EDITION):
                ed = self._safe_subfield(field, 'a')
                if ed:
                    data['edition'] = ed.strip().rstrip('/')
                    break
        except Exception as e:
            logger.debug(f"Could not extract edition: {e}")

        # Language (from 008 field, positions 35-37)
        try:
            field_008 = record[MARCFields.FIXED_LENGTH]
            if field_008:
                val = field_008.value()
                if len(val) >= 38:
                    lang = val[35:38].strip()
                    if lang:
                        data['language'] = lang
        except Exception as e:
            logger.debug(f"Could not extract language: {e}")

        # Physical Description
        try:
            for field in record.get_fields(MARCFields.PHYSICAL_DESC):
                parts = field.get_subfields('a', 'b', 'c')
                if parts:
                    data['physical_description'] = ' '.join(parts)
                    break
        except Exception as e:
            logger.debug(f"Could not extract physical description: {e}")

        # ISSN
        try:
            for field in record.get_fields(MARCFields.ISSN):
                issn = self._safe_subfield(field, 'a')
                if issn:
                    data['issn'] = issn.strip()
                    break
        except Exception as e:
            logger.debug(f"Could not extract ISSN: {e}")

        return data

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    def record_to_dict(self, record: Record, include_full: bool = False) -> Dict[str, Any]:
        """Convert MARC record to dictionary."""
        if not record:
            return {}
        return self.extract_full_fields(record) if include_full else self.extract_minimal_fields(record)

    def record_to_json(self, record: Record) -> str:
        """Convert MARC record to JSON string."""
        try:
            return record.as_json()
        except Exception as e:
            logger.error(f"Failed to convert record to JSON: {e}")
            return "{}"

    def record_to_marc_binary(self, record: Record) -> bytes:
        """Convert MARC record back to binary MARC format."""
        try:
            return record.as_marc()
        except Exception as e:
            logger.error(f"Failed to convert record to binary MARC: {e}")
            return b""

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def deduplicate_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicate records by ISBN or control number.
        Uses O(1) set-based detection. Each ISBN is checked individually
        so records with different ISBN lists still match on shared ISBNs.
        """
        seen_isbns: set = set()
        seen_ctrl: set = set()
        deduplicated: List[Dict[str, Any]] = []

        for rec in records:
            isbn_val = rec.get('isbn')
            ctrl = rec.get('control_number')
            isbns: List[str] = []
            if isinstance(isbn_val, list):
                isbns = isbn_val
            elif isbn_val:
                isbns = [isbn_val]

            # Check if any ISBN or control number was seen before
            is_dup = False
            for isbn in isbns:
                if isbn in seen_isbns:
                    is_dup = True
                    break
            if not is_dup and ctrl and ctrl in seen_ctrl:
                is_dup = True

            if not is_dup:
                deduplicated.append(rec)
                seen_isbns.update(isbns)
                if ctrl:
                    seen_ctrl.add(ctrl)

        logger.debug(f"Deduplicated {len(records)} records to {len(deduplicated)}")
        return deduplicated

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_record(self, record: Record) -> bool:
        """Validate MARC record has a proper leader."""
        try:
            return record is not None and record.leader is not None and len(str(record.leader)) >= 24
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_shared_processor: Optional[MARCProcessor] = None


def get_shared_processor() -> MARCProcessor:
    """Get or create the shared MARCProcessor singleton."""
    global _shared_processor
    if _shared_processor is None:
        _shared_processor = MARCProcessor()
    return _shared_processor


# ---------------------------------------------------------------------------
# Shared ISBN fetch helper (used by holdings, details, export tools)
# ---------------------------------------------------------------------------

def fetch_first_record_by_isbn(conn, isbn: str) -> Tuple[Optional[Record], int]:
    """
    Search for an ISBN on a Z39.50 connection and return the first parsed record.

    Args:
        conn: zoom.Connection object.
        isbn: ISBN to search for.

    Returns:
        (parsed_record_or_None, hit_count)
    """
    from z3950_client.query import get_shared_query_builder

    qbuilder = get_shared_query_builder()
    query = qbuilder.build_ccl_query('isbn', isbn)
    if not query:
        return None, 0

    resultset = conn.search(query)
    hit_count = len(resultset)
    if hit_count == 0:
        return None, 0

    processor = get_shared_processor()
    parsed = processor.parse_zoom_record(resultset[0])
    return parsed, hit_count
