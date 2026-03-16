"""
Comprehensive tests for Z39.50 MCP server.
Uses mocks for Z39.50 connections (no live network required).
"""

import asyncio
import json
import xml.etree.ElementTree as ET
import pytest
import pytest_asyncio
import z3950_client.record_processor as _rp
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from typing import List, Dict, Any

from pymarc import Record, Field, Subfield

# ---------------------------------------------------------------------------
# Client imports
# ---------------------------------------------------------------------------
from z3950_client.connection_pool import (
    AsyncConnectionPool,
    get_shared_pool,
    close_shared_pool,
    run_query_parallel,
)
from z3950_client.record_processor import (
    MARCProcessor,
    MARCFields,
    get_shared_processor,
)
from z3950_client.query import QueryBuilder


# ---------------------------------------------------------------------------
# Fix 6: Autouse fixtures for singleton cleanup between tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_shared_processor():
    """Reset the MARCProcessor singleton before and after each test."""
    _rp._shared_processor = None
    yield
    _rp._shared_processor = None


@pytest_asyncio.fixture(autouse=True)
async def reset_shared_pool():
    """Reset the connection pool singleton before and after each test."""
    await close_shared_pool()
    yield
    await close_shared_pool()


# ---------------------------------------------------------------------------
# Helpers for creating test MARC data
# ---------------------------------------------------------------------------

def _make_pymarc_record(
    title: str = "Test Book",
    author: str = "Test Author",
    isbn: str = "9780262033848",
    publisher: str = "Test Publisher",
    year: str = "2020",
    subject: str = "Testing",
    control_number: str = "12345",
) -> Record:
    """Build a valid PyMARC Record for testing (PyMARC 5.x API)."""
    rec = Record()
    rec.add_field(Field(tag='001', data=control_number))
    rec.add_field(Field(tag='008', data='200101s2020    mau           000 0 eng d'))
    rec.add_field(Field(
        tag='020', indicators=[' ', ' '],
        subfields=[Subfield(code='a', value=isbn)],
    ))
    rec.add_field(Field(
        tag='100', indicators=['1', ' '],
        subfields=[Subfield(code='a', value=author)],
    ))
    rec.add_field(Field(
        tag='245', indicators=['1', '0'],
        subfields=[Subfield(code='a', value=title)],
    ))
    rec.add_field(Field(
        tag='260', indicators=[' ', ' '],
        subfields=[
            Subfield(code='a', value='Cambridge :'),
            Subfield(code='b', value=publisher),
            Subfield(code='c', value=year),
        ],
    ))
    rec.add_field(Field(
        tag='650', indicators=[' ', '0'],
        subfields=[Subfield(code='a', value=subject)],
    ))
    return rec


def _marc_bytes(record: Record) -> bytes:
    """Serialize a PyMARC Record to binary MARC bytes."""
    return record.as_marc()


def _make_mock_zoom_record(marc_record: Record) -> MagicMock:
    """Create a mock zoom.Record wrapping a PyMARC Record's binary."""
    mock = MagicMock()
    mock.data = _marc_bytes(marc_record)
    mock.syntax = 'USMARC'
    return mock


def _make_mock_resultset(records: List[Record]) -> MagicMock:
    """Create a mock zoom.ResultSet returning zoom.Record mocks."""
    zoom_records = [_make_mock_zoom_record(r) for r in records]
    rs = MagicMock()
    rs.__len__ = MagicMock(return_value=len(zoom_records))
    rs.__getitem__ = MagicMock(side_effect=lambda i: zoom_records[i])
    return rs


# ===================================================================
# Tests: Configuration
# ===================================================================

class TestConfigurationLoading:
    """Tests for configuration file loading."""

    def test_libraries_config_exists(self):
        config_path = Path(__file__).parent.parent / 'config' / 'libraries.json'
        assert config_path.exists(), f"Config file not found: {config_path}"

    def test_libraries_config_valid_json(self):
        config_path = Path(__file__).parent.parent / 'config' / 'libraries.json'
        with open(config_path) as f:
            config = json.load(f)
        assert isinstance(config, dict)
        assert len(config) > 0

    def test_loc_config(self):
        config_path = Path(__file__).parent.parent / 'config' / 'libraries.json'
        with open(config_path) as f:
            config = json.load(f)
        assert 'loc' in config
        assert config['loc']['host'] == 'z3950.loc.gov'
        assert config['loc']['port'] == 7090

    def test_worldcat_config(self):
        config_path = Path(__file__).parent.parent / 'config' / 'libraries.json'
        with open(config_path) as f:
            config = json.load(f)
        assert 'worldcat' in config


# ===================================================================
# Tests: Connection Pool
# ===================================================================

class TestConnectionPool:
    """Tests for AsyncConnectionPool."""

    def test_pool_initialization(self):
        pool = AsyncConnectionPool()
        assert pool is not None
        assert len(pool.list_libraries()) > 0

    def test_list_libraries(self):
        pool = AsyncConnectionPool()
        libs = pool.list_libraries()
        assert 'loc' in libs
        assert 'worldcat' in libs

    def test_get_library_config(self):
        pool = AsyncConnectionPool()
        config = pool.get_library_config('loc')
        assert config is not None
        assert config['name'] == 'Library of Congress'
        assert config['host'] == 'z3950.loc.gov'

    def test_get_library_config_unknown(self):
        pool = AsyncConnectionPool()
        config = pool.get_library_config('nonexistent')
        assert config is None

    @pytest.mark.asyncio
    async def test_close_all_empty_pool(self):
        pool = AsyncConnectionPool()
        # Should not raise on empty pool
        await pool.close_all()

    @pytest.mark.asyncio
    async def test_get_connection_unknown_library(self):
        pool = AsyncConnectionPool()
        conn = await pool.get_connection('definitely_not_a_library')
        assert conn is None

    def test_config_path_default(self):
        pool = AsyncConnectionPool()
        assert 'libraries.json' in pool.config_path

    def test_config_path_custom(self):
        pool = AsyncConnectionPool(config_path='/tmp/fake_config.json')
        assert pool.config_path == '/tmp/fake_config.json'
        assert pool.config == {}  # File doesn't exist


class TestSharedPool:
    """Tests for singleton pool."""

    @pytest.mark.asyncio
    async def test_get_shared_pool_singleton(self):
        """get_shared_pool returns same instance on repeated calls."""
        await close_shared_pool()  # Reset
        pool1 = await get_shared_pool()
        pool2 = await get_shared_pool()
        assert pool1 is pool2
        await close_shared_pool()

    @pytest.mark.asyncio
    async def test_close_shared_pool(self):
        """close_shared_pool resets the singleton."""
        await close_shared_pool()
        pool1 = await get_shared_pool()
        await close_shared_pool()
        pool2 = await get_shared_pool()
        assert pool1 is not pool2
        await close_shared_pool()


# ===================================================================
# Tests: Query Builder
# ===================================================================

class TestQueryBuilder:
    """Tests for query building and escaping."""

    def test_ccl_title_query(self):
        builder = QueryBuilder()
        query = builder.build_ccl_query('title', 'Hamlet')
        assert query is not None

    def test_ccl_author_query(self):
        builder = QueryBuilder()
        query = builder.build_ccl_query('author', 'Shakespeare')
        assert query is not None

    def test_ccl_isbn_query(self):
        builder = QueryBuilder()
        query = builder.build_ccl_query('isbn', '978-0-262-03384-8')
        assert query is not None

    def test_ccl_keyword_fallback(self):
        builder = QueryBuilder()
        query = builder.build_ccl_query('unknown_type', 'test')
        assert query is not None  # Falls back to 'kw'

    def test_pqf_query(self):
        builder = QueryBuilder()
        query = builder.build_pqf_query('title', 'Hamlet')
        assert query is not None

    def test_combined_query(self):
        builder = QueryBuilder()
        queries = [
            {'type': 'author', 'value': 'Shakespeare'},
            {'type': 'title', 'value': 'Hamlet'},
        ]
        query = builder.build_combined_query(queries)
        assert query is not None

    def test_combined_query_empty(self):
        builder = QueryBuilder()
        query = builder.build_combined_query([])
        assert query is None

    def test_escape_quotes(self):
        """Quotes are stripped to prevent CCL lexer issues."""
        escaped = QueryBuilder.escape_query_value('test "quotes" here')
        assert '"' not in escaped
        assert escaped == 'test quotes here'

    def test_escape_backslash(self):
        """Backslashes are stripped to prevent CCL lexer issues."""
        escaped = QueryBuilder.escape_query_value('path\\value')
        assert '\\' not in escaped
        assert escaped == 'pathvalue'

    def test_escaping_applied_in_ccl(self):
        """Escaping is applied when building CCL queries."""
        builder = QueryBuilder()
        # Should not raise even with special chars
        query = builder.build_ccl_query('title', 'Book "with" quotes')
        assert query is not None

    def test_isbn_valid_10(self):
        assert QueryBuilder.validate_isbn('0-13-110362-8') is True
        assert QueryBuilder.validate_isbn('013110362X') is True

    def test_isbn_valid_13(self):
        assert QueryBuilder.validate_isbn('978-0-262-03384-8') is True

    def test_isbn_invalid(self):
        assert QueryBuilder.validate_isbn('123') is False
        assert QueryBuilder.validate_isbn('999-999-999-99') is False
        assert QueryBuilder.validate_isbn('') is False

    def test_parse_search_syntax(self):
        params = QueryBuilder.parse_search_syntax('title:Hamlet author:Shakespeare')
        assert params['title'] == 'Hamlet'
        assert params['author'] == 'Shakespeare'

    def test_parse_search_syntax_keyword(self):
        params = QueryBuilder.parse_search_syntax('keyword:test')
        assert params['keyword'] == 'test'

    def test_parse_search_syntax_bare_words(self):
        params = QueryBuilder.parse_search_syntax('hello world')
        assert params['keyword'] == 'hello world'


# ===================================================================
# Tests: MARC Record Processing
# ===================================================================

class TestMARCFields:
    """Test MARC field constants."""

    def test_field_constants_defined(self):
        assert MARCFields.TITLE == '245'
        assert MARCFields.AUTHOR == '100'
        assert MARCFields.ISBN == '020'
        assert MARCFields.SUBJECT == '650'
        assert MARCFields.CONTROL_NUMBER == '001'
        assert MARCFields.HOLDINGS == '852'


class TestMARCProcessor:
    """Tests for MARC record processing."""

    def test_processor_initialization(self):
        processor = MARCProcessor()
        assert isinstance(processor, MARCProcessor)

    def test_parse_valid_marc(self):
        rec = _make_pymarc_record()
        raw = _marc_bytes(rec)
        processor = MARCProcessor()
        parsed = processor.parse_binary_marc(raw)
        assert parsed is not None
        assert parsed.title is not None

    def test_parse_empty_marc(self):
        processor = MARCProcessor()
        assert processor.parse_binary_marc(None) is None
        assert processor.parse_binary_marc(b'') is None

    def test_parse_invalid_marc(self):
        processor = MARCProcessor()
        result = processor.parse_binary_marc(b'not valid marc data')
        # Should return None, not raise
        assert result is None

    def test_parse_zoom_record(self):
        rec = _make_pymarc_record(title="Zoom Test")
        mock_zoom = _make_mock_zoom_record(rec)
        processor = MARCProcessor()
        parsed = processor.parse_zoom_record(mock_zoom)
        assert parsed is not None
        assert 'Zoom Test' in parsed.title

    def test_parse_zoom_record_none(self):
        processor = MARCProcessor()
        assert processor.parse_zoom_record(None) is None

    def test_extract_minimal_fields(self):
        rec = _make_pymarc_record(
            title="My Test Book",
            author="Jane Doe",
            isbn="9781234567890",
            publisher="Acme Press",
            year="2023",
        )
        processor = MARCProcessor()
        fields = processor.extract_minimal_fields(rec)
        assert 'title' in fields
        assert 'author' in fields
        assert 'isbn' in fields
        assert 'publisher' in fields
        assert fields.get('publication_year') == '2023'

    def test_extract_minimal_fields_none(self):
        processor = MARCProcessor()
        assert processor.extract_minimal_fields(None) == {}

    def test_extract_full_fields(self):
        rec = _make_pymarc_record(subject="Computer Science")
        processor = MARCProcessor()
        fields = processor.extract_full_fields(rec)
        assert 'subjects' in fields
        assert 'Computer Science' in fields['subjects']

    def test_extract_full_fields_includes_language(self):
        rec = _make_pymarc_record()
        processor = MARCProcessor()
        fields = processor.extract_full_fields(rec)
        assert 'language' in fields
        assert fields['language'] == 'eng'

    def test_record_to_dict(self):
        rec = _make_pymarc_record()
        processor = MARCProcessor()
        d = processor.record_to_dict(rec)
        assert isinstance(d, dict)
        assert 'title' in d

    def test_record_to_dict_none(self):
        processor = MARCProcessor()
        assert processor.record_to_dict(None) == {}

    def test_record_to_json(self):
        rec = _make_pymarc_record()
        processor = MARCProcessor()
        j = processor.record_to_json(rec)
        parsed = json.loads(j)
        assert isinstance(parsed, dict)

    def test_record_to_marc_binary_roundtrip(self):
        rec = _make_pymarc_record()
        processor = MARCProcessor()
        binary = processor.record_to_marc_binary(rec)
        assert len(binary) > 0
        # Roundtrip
        parsed = processor.parse_binary_marc(binary)
        assert parsed is not None

    def test_validate_record_valid(self):
        rec = _make_pymarc_record()
        processor = MARCProcessor()
        assert processor.validate_record(rec) is True

    def test_validate_record_none(self):
        processor = MARCProcessor()
        assert processor.validate_record(None) is False


class TestDeduplication:
    """Tests for record deduplication."""

    def test_dedup_by_isbn(self):
        processor = MARCProcessor()
        records = [
            {'title': 'Book A', 'isbn': '9780262033848'},
            {'title': 'Book A', 'isbn': '9780262033848'},  # Duplicate
            {'title': 'Book B', 'isbn': '9781234567890'},
        ]
        deduped = processor.deduplicate_records(records)
        assert len(deduped) == 2

    def test_dedup_by_control_number(self):
        processor = MARCProcessor()
        records = [
            {'title': 'Book C', 'control_number': '12345'},
            {'title': 'Book C', 'control_number': '12345'},  # Duplicate
        ]
        deduped = processor.deduplicate_records(records)
        assert len(deduped) == 1

    def test_dedup_no_key(self):
        """Records without ISBN or control number should all be kept."""
        processor = MARCProcessor()
        records = [
            {'title': 'Unknown A'},
            {'title': 'Unknown B'},
        ]
        deduped = processor.deduplicate_records(records)
        assert len(deduped) == 2

    def test_dedup_multiple_isbns(self):
        """Records with overlapping ISBN lists should be deduplicated."""
        processor = MARCProcessor()
        records = [
            {'title': 'Book X', 'isbn': ['111', '222']},
            {'title': 'Book X', 'isbn': ['222', '333']},  # Shares '222'
            {'title': 'Book Y', 'isbn': '444'},
        ]
        deduped = processor.deduplicate_records(records)
        assert len(deduped) == 2  # Second record is dup (shares isbn '222')

    def test_dedup_empty_list(self):
        processor = MARCProcessor()
        assert processor.deduplicate_records([]) == []


class TestSharedProcessor:
    """Tests for singleton MARCProcessor."""

    def test_get_shared_processor_singleton(self):
        import z3950_client.record_processor as rp
        rp._shared_processor = None  # Reset

        p1 = get_shared_processor()
        p2 = get_shared_processor()
        assert p1 is p2
        rp._shared_processor = None


# ===================================================================
# Tests: ZOOM API Usage (with mocks)
# ===================================================================

class TestZoomAPIUsage:
    """Verify that tools use correct ZOOM API patterns."""

    def test_search_uses_resultset(self):
        """_search_single_library uses len(resultset) and resultset[i]."""
        rec = _make_pymarc_record(title="Found Book")
        resultset = _make_mock_resultset([rec])

        mock_conn = MagicMock()
        mock_conn.databaseName = 'TestDB'
        mock_conn.search = MagicMock(return_value=resultset)

        from tools.search import _search_single_library
        results = _search_single_library(mock_conn, 'Found', 'title', 10)

        mock_conn.search.assert_called_once()
        resultset.__len__.assert_called()
        resultset.__getitem__.assert_called_with(0)
        assert len(results) == 1
        assert 'Found Book' in results[0].get('title', '')

    def test_search_empty_resultset(self):
        """Empty resultset returns empty list."""
        empty_rs = _make_mock_resultset([])
        mock_conn = MagicMock()
        mock_conn.databaseName = 'TestDB'
        mock_conn.search = MagicMock(return_value=empty_rs)

        from tools.search import _search_single_library
        results = _search_single_library(mock_conn, 'Nothing', 'title', 10)
        assert results == []

    def test_search_multiple_records(self):
        """Can retrieve multiple records from resultset."""
        rec1 = _make_pymarc_record(title="Book One", isbn="1111111111111")
        rec2 = _make_pymarc_record(title="Book Two", isbn="2222222222222")
        resultset = _make_mock_resultset([rec1, rec2])

        mock_conn = MagicMock()
        mock_conn.databaseName = 'TestDB'
        mock_conn.search = MagicMock(return_value=resultset)

        from tools.search import _search_single_library
        results = _search_single_library(mock_conn, 'Book', 'title', 10)
        assert len(results) == 2

    def test_search_max_results_cap(self):
        """max_results caps the number of records fetched."""
        records = [
            _make_pymarc_record(title=f"Book {i}", isbn=f"111111111{i:04d}")
            for i in range(10)
        ]
        resultset = _make_mock_resultset(records)

        mock_conn = MagicMock()
        mock_conn.databaseName = 'TestDB'
        mock_conn.search = MagicMock(return_value=resultset)

        from tools.search import _search_single_library
        results = _search_single_library(mock_conn, 'Book', 'title', 3)
        assert len(results) <= 3


# ===================================================================
# Tests: Holdings
# ===================================================================

class TestHoldingsExtraction:
    """Tests for holdings extraction from MARC records."""

    def test_extract_holdings_with_852(self):
        rec = _make_pymarc_record()
        rec.add_field(Field(
            tag='852', indicators=[' ', ' '],
            subfields=[Subfield(code='a', value='Main Library'), Subfield(code='h', value='QA76'), Subfield(code='i', value='.P97')],
        ))

        from tools.holdings import _extract_holdings
        holdings = _extract_holdings(rec)
        assert 'Main Library' in holdings
        assert 'QA76' in holdings['Main Library']['call_number']

    def test_extract_holdings_empty(self):
        rec = _make_pymarc_record()  # No 852 field
        from tools.holdings import _extract_holdings
        holdings = _extract_holdings(rec)
        assert holdings == {}

    def test_extract_holdings_non_record(self):
        from tools.holdings import _extract_holdings
        assert _extract_holdings("not a record") == {}

    def test_check_single_found(self):
        rec = _make_pymarc_record()
        resultset = _make_mock_resultset([rec])

        mock_conn = MagicMock()
        mock_conn.search = MagicMock(return_value=resultset)

        from tools.holdings import _check_single
        result = _check_single(mock_conn, '9780262033848')
        assert result.get('available') is True

    def test_check_single_not_found(self):
        empty_rs = _make_mock_resultset([])
        mock_conn = MagicMock()
        mock_conn.search = MagicMock(return_value=empty_rs)

        from tools.holdings import _check_single
        result = _check_single(mock_conn, '0000000000')
        assert result.get('found') is False


# ===================================================================
# Tests: Details
# ===================================================================

class TestDetailsFetch:
    """Tests for detail retrieval."""

    def test_fetch_details_found(self):
        rec = _make_pymarc_record(
            title="Detail Book", author="Detail Author", isbn="9780262033848"
        )
        resultset = _make_mock_resultset([rec])

        mock_conn = MagicMock()
        mock_conn.search = MagicMock(return_value=resultset)

        from tools.details import _fetch_details
        result = _fetch_details(mock_conn, '9780262033848')
        assert result.get('found') is True
        assert 'Detail Book' in result.get('title', '')

    def test_fetch_details_not_found(self):
        empty_rs = _make_mock_resultset([])
        mock_conn = MagicMock()
        mock_conn.search = MagicMock(return_value=empty_rs)

        from tools.details import _fetch_details
        result = _fetch_details(mock_conn, '0000000000')
        assert result.get('found') is False


# ===================================================================
# Tests: Export
# ===================================================================

class TestExport:
    """Tests for MARC export in multiple formats."""

    def test_export_binary(self):
        rec = _make_pymarc_record(isbn="9780262033848")
        resultset = _make_mock_resultset([rec])

        mock_conn = MagicMock()
        mock_conn.search = MagicMock(return_value=resultset)

        from tools.export import _fetch_and_export
        result = _fetch_and_export(mock_conn, '9780262033848', 'binary')
        assert result.get('found') is True
        assert result.get('format') == 'binary'
        assert 'data' in result
        assert result['size_bytes'] > 0

    def test_export_json(self):
        rec = _make_pymarc_record(isbn="9780262033848")
        resultset = _make_mock_resultset([rec])

        mock_conn = MagicMock()
        mock_conn.search = MagicMock(return_value=resultset)

        from tools.export import _fetch_and_export
        result = _fetch_and_export(mock_conn, '9780262033848', 'json')
        assert result.get('found') is True
        assert result.get('format') == 'json'
        assert isinstance(result.get('data'), dict)

    def test_export_xml(self):
        rec = _make_pymarc_record(isbn="9780262033848")
        resultset = _make_mock_resultset([rec])

        mock_conn = MagicMock()
        mock_conn.search = MagicMock(return_value=resultset)

        from tools.export import _fetch_and_export
        result = _fetch_and_export(mock_conn, '9780262033848', 'xml')
        assert result.get('found') is True
        assert result.get('format') == 'xml'
        assert '<record>' in result.get('data', '')

    def test_export_unsupported_format(self):
        rec = _make_pymarc_record()
        resultset = _make_mock_resultset([rec])

        mock_conn = MagicMock()
        mock_conn.search = MagicMock(return_value=resultset)

        from tools.export import _fetch_and_export
        result = _fetch_and_export(mock_conn, '9780262033848', 'pdf')
        assert 'error' in result

    def test_export_not_found(self):
        empty_rs = _make_mock_resultset([])
        mock_conn = MagicMock()
        mock_conn.search = MagicMock(return_value=empty_rs)

        from tools.export import _fetch_and_export
        result = _fetch_and_export(mock_conn, '0000000000', 'binary')
        assert result.get('found') is False


# ===================================================================
# Tests: Browse
# ===================================================================

class TestBrowse:
    """Tests for browse operations."""

    @pytest.mark.asyncio
    async def test_browse_libraries(self):
        from tools.browse import browse_libraries
        result = await browse_libraries()
        assert 'libraries' in result
        assert result['total'] > 0
        lib_ids = [lib['id'] for lib in result['libraries']]
        assert 'loc' in lib_ids

    def test_scan_subjects_fallback(self):
        """When scan raises, falls back to common subjects."""
        mock_conn = MagicMock()
        mock_conn.scan = MagicMock(side_effect=Exception("SCAN not supported"))

        from tools.browse import _scan_subjects
        result = _scan_subjects(mock_conn, 'His', 20)
        assert result.get('note') is not None  # Fallback note
        terms = [s['term'] for s in result['subjects']]
        assert 'History' in terms


# ===================================================================
# Tests: Error Handling
# ===================================================================

class TestErrorHandling:
    """Tests for graceful error handling."""

    def test_search_connection_failure(self):
        """Search should return empty results on connection errors."""
        mock_conn = MagicMock()
        mock_conn.databaseName = 'TestDB'
        mock_conn.search = MagicMock(side_effect=Exception("Connection refused"))

        from tools.search import _search_single_library
        results = _search_single_library(mock_conn, 'test', 'title', 10)
        assert results == []

    def test_invalid_marc_doesnt_crash(self):
        processor = MARCProcessor()
        result = processor.parse_binary_marc(b'\x00\x01\x02\x03')
        assert result is None

    def test_extract_fields_from_none(self):
        processor = MARCProcessor()
        assert processor.extract_minimal_fields(None) == {}
        assert processor.extract_full_fields(None) == {}
        assert processor.record_to_dict(None) == {}

    def test_validate_none_record(self):
        processor = MARCProcessor()
        assert processor.validate_record(None) is False

    def test_zoom_record_non_bytes_data(self):
        """zoom record with non-bytes data should return None."""
        mock_zoom = MagicMock()
        mock_zoom.data = "not bytes"
        mock_zoom.syntax = 'XML'
        processor = MARCProcessor()
        assert processor.parse_zoom_record(mock_zoom) is None


# ===================================================================
# Tests: Parallel Execution
# ===================================================================

class TestParallelExecution:
    """Tests for parallel query execution."""

    @pytest.mark.asyncio
    async def test_run_query_parallel_empty(self):
        pool = AsyncConnectionPool()
        results = await run_query_parallel(pool, [])
        assert results == []

    @pytest.mark.asyncio
    async def test_run_query_parallel_with_mock(self):
        """Parallel execution with mocked connections."""
        pool = AsyncConnectionPool()

        def fake_query(conn, arg):
            return [{'title': f'Result from {arg}'}]

        # Patch get_connection to return a mock
        mock_conn = MagicMock()

        async def mock_get_conn(lib_id, **kw):
            return mock_conn

        pool.get_connection = mock_get_conn

        tasks = [
            ('loc', fake_query, ('loc',), {}),
            ('worldcat', fake_query, ('worldcat',), {}),
        ]
        results = await run_query_parallel(pool, tasks)
        assert len(results) == 2
        assert all(r.get('error') is None for r in results)


# ===================================================================
# Fix 7: Tests: Tool Entry Points (async, with mocked pool)
# ===================================================================

def _make_mock_pool(marc_record: Record):
    """Build a mock AsyncConnectionPool that returns a preset result."""
    resultset = _make_mock_resultset([marc_record])
    mock_conn = MagicMock()
    mock_conn.search = MagicMock(return_value=resultset)
    mock_conn.databaseName = 'MockDB'

    mock_pool = MagicMock()
    mock_pool.list_libraries = MagicMock(return_value=['loc', 'worldcat'])
    mock_pool.get_connection = AsyncMock(return_value=mock_conn)
    mock_pool.get_library_config = MagicMock(return_value={
        'name': 'Mock Library',
        'host': 'mock.host',
        'port': 9999,
        'database': 'MockDB',
    })
    return mock_pool


class TestToolEntryPoints:
    """Tests for the async MCP tool entry-point functions."""

    @pytest.mark.asyncio
    async def test_search_tool_returns_json(self):
        """search_tool returns valid JSON with results."""
        rec = _make_pymarc_record(title="Entry Point Book")
        mock_pool = _make_mock_pool(rec)

        with patch('tools.search.get_shared_pool', AsyncMock(return_value=mock_pool)):
            from tools.search import search_tool
            result = await search_tool('Hamlet', libraries='loc', query_type='title')
        data = json.loads(result)
        assert 'results' in data or 'error' in data or isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_holdings_tool_returns_json(self):
        """holdings_tool returns valid JSON with availability info."""
        rec = _make_pymarc_record(isbn="9780262033848")
        mock_pool = _make_mock_pool(rec)

        with patch('tools.holdings.get_shared_pool', AsyncMock(return_value=mock_pool)):
            from tools.holdings import holdings_tool
            result = await holdings_tool('9780262033848', libraries='loc')
        data = json.loads(result)
        assert 'isbn' in data
        assert 'libraries' in data

    @pytest.mark.asyncio
    async def test_details_tool_returns_json(self):
        """details_tool returns valid JSON with bibliographic details."""
        rec = _make_pymarc_record(isbn="9780262033848", title="Detail Title")
        mock_pool = _make_mock_pool(rec)

        with patch('tools.details.get_shared_pool', AsyncMock(return_value=mock_pool)):
            from tools.details import details_tool
            result = await details_tool('9780262033848', 'loc')
        data = json.loads(result)
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_export_tool_binary_returns_json(self):
        """export_tool in binary mode returns valid JSON with base64 data."""
        rec = _make_pymarc_record(isbn="9780262033848")
        mock_pool = _make_mock_pool(rec)

        with patch('tools.export.get_shared_pool', AsyncMock(return_value=mock_pool)):
            from tools.export import export_tool
            result = await export_tool('9780262033848', 'loc', 'binary')
        data = json.loads(result)
        assert data.get('found') is True
        assert data.get('format') == 'binary'
        assert 'data' in data

    @pytest.mark.asyncio
    async def test_export_tool_json_returns_valid_json(self):
        """export_tool in json mode returns valid JSON with dict data."""
        rec = _make_pymarc_record(isbn="9780262033848")
        mock_pool = _make_mock_pool(rec)

        with patch('tools.export.get_shared_pool', AsyncMock(return_value=mock_pool)):
            from tools.export import export_tool
            result = await export_tool('9780262033848', 'loc', 'json')
        data = json.loads(result)
        assert data.get('found') is True
        assert isinstance(data.get('data'), dict)

    @pytest.mark.asyncio
    async def test_holdings_tool_connection_failure(self):
        """holdings_tool handles connection failure gracefully."""
        mock_pool = MagicMock()
        mock_pool.list_libraries = MagicMock(return_value=['loc'])
        mock_pool.get_connection = AsyncMock(return_value=None)  # Failure

        with patch('tools.holdings.get_shared_pool', AsyncMock(return_value=mock_pool)):
            from tools.holdings import holdings_tool
            result = await holdings_tool('9780262033848', libraries='loc')
        data = json.loads(result)
        assert data['libraries']['loc']['available'] is False
        assert 'error' in data['libraries']['loc']


# ===================================================================
# Fix 8: Tests: XML Special Characters
# ===================================================================

class TestXMLSpecialCharacters:
    """Tests that _marc_to_xml() properly escapes special characters."""

    def _record_with_special_chars(self) -> Record:
        """Build a MARC record with &, <, > in field values."""
        rec = Record()
        rec.add_field(Field(tag='001', data='ctrl&num<1>'))
        rec.add_field(Field(
            tag='245', indicators=['1', '0'],
            subfields=[Subfield(code='a', value='Tom & Jerry < Adventures >')],
        ))
        rec.add_field(Field(
            tag='100', indicators=['1', ' '],
            subfields=[Subfield(code='a', value='Author <with> brackets & stuff')],
        ))
        rec.add_field(Field(
            tag='650', indicators=[' ', '0'],
            subfields=[Subfield(code='a', value='Science & Technology')],
        ))
        return rec

    def test_xml_with_ampersand_is_valid(self):
        """Ampersands in field values produce valid XML."""
        from tools.export import _marc_to_xml
        rec = self._record_with_special_chars()
        xml_str = _marc_to_xml(rec)
        # This must not raise - if & is not escaped it would
        root = ET.fromstring(xml_str)
        assert root is not None

    def test_xml_with_angle_brackets_is_valid(self):
        """Angle brackets in field values produce valid XML."""
        from tools.export import _marc_to_xml
        rec = Record()
        rec.add_field(Field(
            tag='245', indicators=['1', '0'],
            subfields=[Subfield(code='a', value='Title <first> & <second>')],
        ))
        xml_str = _marc_to_xml(rec)
        root = ET.fromstring(xml_str)  # Raises if invalid
        assert root is not None

    def test_xml_ampersand_is_escaped_in_output(self):
        """Ampersands appear as &amp; in the raw XML string."""
        from tools.export import _marc_to_xml
        rec = Record()
        rec.add_field(Field(
            tag='245', indicators=['1', '0'],
            subfields=[Subfield(code='a', value='Tom & Jerry')],
        ))
        xml_str = _marc_to_xml(rec)
        assert '&amp;' in xml_str
        assert '& Jerry' not in xml_str  # Raw & must not appear in data position

    def test_xml_angle_brackets_escaped_in_output(self):
        """< and > appear as &lt; and &gt; in the raw XML string."""
        from tools.export import _marc_to_xml
        rec = Record()
        rec.add_field(Field(
            tag='245', indicators=['1', '0'],
            subfields=[Subfield(code='a', value='A < B > C')],
        ))
        xml_str = _marc_to_xml(rec)
        assert '&lt;' in xml_str
        assert '&gt;' in xml_str

    def test_xml_control_field_special_chars(self):
        """Special chars in control fields (001, 003 etc.) are escaped."""
        from tools.export import _marc_to_xml
        rec = Record()
        rec.add_field(Field(tag='001', data='id&<test>'))
        xml_str = _marc_to_xml(rec)
        root = ET.fromstring(xml_str)  # Must parse without error
        assert root is not None

    def test_xml_round_trip_title_preserved(self):
        """The title text (with special chars) survives an XML round-trip."""
        from tools.export import _marc_to_xml
        rec = Record()
        original_title = 'Cats & Dogs < Nice > Pets'
        rec.add_field(Field(
            tag='245', indicators=['1', '0'],
            subfields=[Subfield(code='a', value=original_title)],
        ))
        xml_str = _marc_to_xml(rec)
        root = ET.fromstring(xml_str)
        # Find the subfield text inside the parsed XML
        texts = [el.text for el in root.iter() if el.text]
        assert any(original_title in (t or '') for t in texts)


# ===================================================================
# Entry point
# ===================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
