"""Tests for shots.utils module."""

from __future__ import annotations

import re

import pytest

from shots.utils import (
    StepOutcome,
    compact_json,
    is_http_url,
    normalize_url,
    now_ts,
    safe_filename,
    same_origin,
)


class TestNowTs:
    def test_returns_string(self):
        result = now_ts()
        assert isinstance(result, str)

    def test_format_matches_expected_pattern(self):
        result = now_ts()
        # Format: YYYYMMDD-HHMMSS
        assert re.match(r"^\d{8}-\d{6}$", result)


class TestSafeFilename:
    @pytest.mark.parametrize(
        "input_name,expected",
        [
            ("Dashboard Hero", "dashboard-hero"),
            ("  UPPER CASE  ", "upper-case"),
            ("special@#$chars!", "special-chars"),
            ("multiple---dashes", "multiple-dashes"),
            ("", "shot"),
            ("a" * 200, "a" * 120),
        ],
    )
    def test_safe_filename_variations(self, input_name: str, expected: str):
        result = safe_filename(input_name)
        assert result == expected

    def test_none_input_returns_shot(self):
        # safe_filename handles None via (name or "")
        result = safe_filename(None)  # type: ignore[arg-type]
        assert result == "shot"

    def test_max_len_parameter(self):
        result = safe_filename("a" * 50, max_len=10)
        assert len(result) == 10

    def test_preserves_underscores_and_dots(self):
        result = safe_filename("file_name.test")
        assert result == "file_name.test"


class TestNormalizeUrl:
    @pytest.mark.parametrize(
        "input_url,expected",
        [
            ("https://example.com/page#section", "https://example.com/page"),
            ("https://example.com/page?query=1#section", "https://example.com/page?query=1"),
            ("https://example.com/page", "https://example.com/page"),
            ("https://example.com/#hash", "https://example.com/"),
        ],
    )
    def test_removes_fragments(self, input_url: str, expected: str):
        assert normalize_url(input_url) == expected


class TestIsHttpUrl:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://example.com", True),
            ("http://example.com", True),
            ("HTTPS://EXAMPLE.COM", True),
            ("ftp://example.com", False),
            ("file:///path/to/file", False),
            ("not a url", False),
            ("", False),
            ("javascript:alert(1)", False),
        ],
    )
    def test_is_http_url(self, url: str, expected: bool):
        assert is_http_url(url) == expected


class TestSameOrigin:
    @pytest.mark.parametrize(
        "url_a,url_b,expected",
        [
            ("https://example.com/page1", "https://example.com/page2", True),
            ("https://example.com/", "https://example.com/deep/path", True),
            ("https://example.com:443", "https://example.com:443/path", True),
            ("https://example.com", "http://example.com", False),
            ("https://a.example.com", "https://b.example.com", False),
            ("https://example.com:8080", "https://example.com:8081", False),
        ],
    )
    def test_same_origin(self, url_a: str, url_b: str, expected: bool):
        assert same_origin(url_a, url_b) == expected


class TestCompactJson:
    def test_compact_output(self):
        obj = {"key": "value", "list": [1, 2, 3]}
        result = compact_json(obj)
        assert result == '{"key":"value","list":[1,2,3]}'

    def test_unicode_preserved(self):
        obj = {"emoji": "\U0001f389"}
        result = compact_json(obj)
        assert "\U0001f389" in result

    def test_no_extra_whitespace(self):
        obj = {"a": 1, "b": 2}
        result = compact_json(obj)
        assert " " not in result


class TestStepOutcome:
    def test_ok_outcome(self):
        outcome = StepOutcome(ok=True)
        assert outcome.ok is True
        assert outcome.error is None
        assert outcome.extra is None

    def test_error_outcome(self):
        outcome = StepOutcome(ok=False, error="Something failed")
        assert outcome.ok is False
        assert outcome.error == "Something failed"

    def test_with_extra(self):
        outcome = StepOutcome(ok=True, extra={"terminal": "done"})
        assert outcome.extra == {"terminal": "done"}
