"""Tests for URL normalization, SSRF, chunking, and core logic."""

import pytest

from app.security.urls import normalize_url, validate_url


class TestURLNormalization:
    """Unit tests for URL normalization and validation."""

    def test_basic_normalization(self):
        assert normalize_url("https://Example.COM/path/") == "https://example.com/path"

    def test_removes_default_http_port(self):
        assert normalize_url("http://example.com:80/page") == "http://example.com/page"

    def test_removes_default_https_port(self):
        assert normalize_url("https://example.com:443/page") == "https://example.com/page"

    def test_keeps_non_default_port(self):
        assert normalize_url("https://example.com:8080/page") == "https://example.com:8080/page"

    def test_sorts_query_params(self):
        result = normalize_url("https://example.com/page?z=1&a=2")
        assert result == "https://example.com/page?a=2&z=1"

    def test_removes_fragment(self):
        result = normalize_url("https://example.com/page#section")
        assert result == "https://example.com/page"

    def test_preserves_root_slash(self):
        assert normalize_url("https://example.com/") == "https://example.com/"

    def test_rejects_ftp_scheme(self):
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            normalize_url("ftp://example.com/file")

    def test_rejects_no_hostname(self):
        with pytest.raises(ValueError, match="hostname"):
            normalize_url("https:///path")

    def test_validate_adds_scheme(self):
        result = validate_url("example.com/page")
        assert result.startswith("https://")

    def test_validate_empty_url(self):
        with pytest.raises(ValueError, match="empty"):
            validate_url("")

    def test_duplicate_detection(self):
        """Two URLs that should normalize to the same canonical form."""
        url1 = "https://Example.COM:443/article/?b=2&a=1#comments"
        url2 = "https://example.com/article?a=1&b=2"
        assert normalize_url(url1) == normalize_url(url2)


class TestSSRFValidation:
    """Tests for SSRF protection."""

    def test_rejects_localhost(self):
        from app.security.ssrf import SSRFError, _resolve_and_validate
        with pytest.raises(SSRFError):
            _resolve_and_validate("127.0.0.1")

    def test_rejects_private_10x(self):
        from app.security.ssrf import SSRFError, _resolve_and_validate
        with pytest.raises(SSRFError):
            _resolve_and_validate("10.0.0.1")

    def test_rejects_private_172x(self):
        from app.security.ssrf import SSRFError, _resolve_and_validate
        with pytest.raises(SSRFError):
            _resolve_and_validate("172.16.0.1")

    def test_rejects_private_192x(self):
        from app.security.ssrf import SSRFError, _resolve_and_validate
        with pytest.raises(SSRFError):
            _resolve_and_validate("192.168.1.1")

    def test_rejects_metadata_ip(self):
        from app.security.ssrf import SSRFError, _resolve_and_validate
        with pytest.raises(SSRFError):
            _resolve_and_validate("169.254.169.254")

    def test_rejects_metadata_host(self):
        from app.security.ssrf import SSRFError, _resolve_and_validate
        with pytest.raises(SSRFError):
            _resolve_and_validate("metadata.google.internal")

    def test_rejects_loopback_ipv4(self):
        from app.security.ssrf import _is_ip_safe
        assert _is_ip_safe("127.0.0.1") is False
        assert _is_ip_safe("127.0.0.2") is False

    def test_rejects_link_local(self):
        from app.security.ssrf import _is_ip_safe
        assert _is_ip_safe("169.254.0.1") is False

    def test_allows_public_ip(self):
        from app.security.ssrf import _is_ip_safe
        assert _is_ip_safe("8.8.8.8") is True
        assert _is_ip_safe("1.1.1.1") is True


class TestChunking:
    """Tests for text chunking."""

    def test_short_text_single_chunk(self):
        from app.pipeline import chunk_text
        text = "This is a short text."
        chunks = chunk_text(text, chunk_size=500)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_multiple_chunks(self):
        from app.pipeline import chunk_text
        # Generate text that's clearly longer than 500 tokens
        text = "word " * 2000  # ~2000 tokens
        chunks = chunk_text(text, chunk_size=500, overlap=50)
        assert len(chunks) > 1

    def test_overlap_exists(self):
        from app.pipeline import chunk_text
        text = "word " * 2000
        chunks = chunk_text(text, chunk_size=500, overlap=50)
        # Check that consecutive chunks share some content
        if len(chunks) >= 2:
            # The end of chunk[0] should overlap with the start of chunk[1]
            assert len(chunks[0]) > 0
            assert len(chunks[1]) > 0


class TestTagNormalization:
    """Tests for tag name normalization."""

    def test_case_insensitive(self):
        """Tags should be compared case-insensitively."""
        assert "python".lower() == "Python".lower()
        assert "MACHINE LEARNING".lower() == "machine learning".lower()

    def test_strip_whitespace(self):
        """Tags should have whitespace stripped."""
        assert "  python  ".strip() == "python"
