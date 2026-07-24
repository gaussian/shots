"""Tests for shots.labels module."""

from __future__ import annotations

from shots.labels import desensitize_url, render_label


class TestDesensitizeUrl:
    def test_strips_base_url_prefix(self):
        result = desensitize_url("https://example.com/app/dashboard", "https://example.com")
        assert result == "/app/dashboard"

    def test_replaces_uuid_segment(self):
        url = "http://localhost:4210/brain/accounts/user/edfb2590-1234-4abc-8def-0123456789ab/change/"
        result = desensitize_url(url, "http://localhost:4210")
        assert result == "/brain/accounts/user/{id}/change/"

    def test_replaces_numeric_id_segment(self):
        result = desensitize_url("https://example.com/orders/12345", "https://example.com")
        assert result == "/orders/{id}"

    def test_replaces_trailing_numeric_id(self):
        result = desensitize_url("https://example.com/orders/12345/", "https://example.com")
        assert result == "/orders/{id}/"

    def test_replaces_multiple_numeric_ids(self):
        result = desensitize_url("https://example.com/accounts/1/orders/42", "https://example.com")
        assert result == "/accounts/{id}/orders/{id}"

    def test_replaces_uuid_before_numeric(self):
        url = "https://example.com/users/a1b2c3d4-1111-2222-3333-444455556666/orders/42"
        result = desensitize_url(url, "https://example.com")
        assert result == "/users/{id}/orders/{id}"

    def test_no_base_url_uses_urlparse_path(self):
        result = desensitize_url("https://example.com/settings/42")
        assert result == "/settings/{id}"

    def test_url_not_starting_with_base_url_uses_urlparse(self):
        # base_url provided but doesn't match the actual url prefix
        result = desensitize_url("https://other.com/settings/42", "https://example.com")
        assert result == "/settings/{id}"

    def test_empty_path_defaults_to_root(self):
        result = desensitize_url("https://example.com", "https://example.com")
        assert result == "/"

    def test_no_ids_in_path_unchanged(self):
        result = desensitize_url("https://example.com/dashboard", "https://example.com")
        assert result == "/dashboard"

    def test_case_insensitive_uuid(self):
        url = "https://example.com/x/ABCDEF12-1234-4ABC-8DEF-0123456789AB"
        result = desensitize_url(url, "https://example.com")
        assert result == "/x/{id}"


class TestRenderLabel:
    def test_renders_known_variables(self):
        result = render_label("{title} - {url}", {"url": "/dashboard", "id": "x", "title": "Dashboard"})
        assert result == "Dashboard - /dashboard"

    def test_unknown_tags_left_as_is(self):
        result = render_label("{title} {unknown}", {"url": "/x", "id": "1", "title": "T"})
        assert result == "T {unknown}"

    def test_no_variables_used(self):
        result = render_label("Static label", {"url": "/x", "id": "1", "title": "T"})
        assert result == "Static label"

    def test_all_three_variables(self):
        result = render_label(
            "{id}: {title} ({url})",
            {"url": "/accounts/{id}", "id": "acct-1", "title": "Account page"},
        )
        assert result == "acct-1: Account page (/accounts/{id})"

    def test_missing_variable_key_preserved(self):
        # variables dict doesn't include "title" at all
        result = render_label("{title}", {"url": "/x", "id": "1"})
        assert result == "{title}"
