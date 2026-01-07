"""Tests for database repository functions (hash/normalize)."""

from argus.db.repository import hash_text, hash_url, normalize_url


class TestNormalizeUrl:
    """Tests for normalize_url function."""

    def test_removes_trailing_slash(self) -> None:
        """Test trailing slash removal."""
        assert normalize_url("example.com/path/") == "example.com/path"

    def test_lowercases_url(self) -> None:
        """Test URL lowercasing."""
        assert normalize_url("EXAMPLE.COM/Path") == "example.com/path"

    def test_removes_https_prefix(self) -> None:
        """Test https:// removal."""
        assert normalize_url("https://example.com") == "example.com"

    def test_removes_http_prefix(self) -> None:
        """Test http:// removal."""
        assert normalize_url("http://example.com") == "example.com"

    def test_removes_www_prefix(self) -> None:
        """Test www. removal."""
        assert normalize_url("www.example.com") == "example.com"

    def test_removes_https_and_www(self) -> None:
        """Test combined https:// and www. removal."""
        assert normalize_url("https://www.example.com/page") == "example.com/page"

    def test_strips_whitespace(self) -> None:
        """Test whitespace stripping."""
        assert normalize_url("  example.com  ") == "example.com"


class TestHashUrl:
    """Tests for hash_url function."""

    def test_returns_64_char_hex(self) -> None:
        """Test that hash is 64 character hex string (SHA256)."""
        result = hash_url("https://example.com")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_url_same_hash(self) -> None:
        """Test deterministic hashing."""
        url = "https://example.com/article"
        assert hash_url(url) == hash_url(url)

    def test_different_urls_different_hash(self) -> None:
        """Test different URLs produce different hashes."""
        assert hash_url("https://example.com/a") != hash_url("https://example.com/b")

    def test_normalized_variants_same_hash(self) -> None:
        """Test that normalized variants produce same hash."""
        url1 = "https://www.example.com/page/"
        url2 = "http://example.com/page"
        url3 = "HTTPS://WWW.EXAMPLE.COM/page"

        hash1 = hash_url(url1)
        hash2 = hash_url(url2)
        hash3 = hash_url(url3)

        assert hash1 == hash2 == hash3


class TestHashText:
    """Tests for hash_text function."""

    def test_returns_64_char_hex(self) -> None:
        """Test that hash is 64 character hex string (SHA256)."""
        result = hash_text("Title", "Snippet")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_text_same_hash(self) -> None:
        """Test deterministic hashing."""
        assert hash_text("Title", "Snippet") == hash_text("Title", "Snippet")

    def test_different_text_different_hash(self) -> None:
        """Test different text produces different hashes."""
        assert hash_text("Title A", "Snippet") != hash_text("Title B", "Snippet")

    def test_case_insensitive(self) -> None:
        """Test that hashing is case insensitive."""
        assert hash_text("TITLE", "SNIPPET") == hash_text("title", "snippet")

    def test_without_snippet(self) -> None:
        """Test hashing with title only."""
        result = hash_text("Title Only")
        assert len(result) == 64
        assert hash_text("Title Only") == hash_text("TITLE ONLY")

    def test_strips_whitespace(self) -> None:
        """Test whitespace stripping."""
        assert hash_text("  title  ", "  snippet  ") == hash_text("title", "snippet")
