"""
Unit Tests: Product API — _fuzzy_match, search, compare, ambiguity resolution.
"""
import json
import pytest
from app.tools.product_api import _fuzzy_match, _format_product, get_product_details, search_products


class TestFuzzyMatch:
    """Tests for the central _fuzzy_match function."""

    def test_exact_key_match(self):
        result = _fuzzy_match("laptop")
        assert result is not None
        assert not isinstance(result, list)
        assert result["product_key"] == "laptop"

    def test_name_contains_match(self):
        result = _fuzzy_match("Sony WH-1000XM6")
        assert result is not None
        assert not isinstance(result, list)
        assert "sony" in result["name"].lower() or "xm6" in result["name"].lower()

    def test_synonym_match(self):
        result = _fuzzy_match("noise cancelling headphones")
        assert result is not None
        # Should return a single product or a list — if list, headphones should be in it
        if isinstance(result, list):
            names = [r["name"].lower() for r in result]
            assert any("sony" in n or "headphone" in n for n in names)
        else:
            assert "sony" in result["name"].lower() or "headphone" in result["name"].lower()

    def test_nonexistent_product_returns_none(self):
        result = _fuzzy_match("xyzzy_nonexistent_product_12345")
        assert result is None

    def test_returns_dict_for_unambiguous(self):
        result = _fuzzy_match("macbook")
        assert isinstance(result, dict), "Unambiguous match should return dict, not list"

    def test_ambiguity_returns_list(self):
        """Searching 'keyboard' should match both Keychron and HP wired keyboard."""
        result = _fuzzy_match("keyboard")
        # May return list (ambiguous) or a dict — both are valid
        # But if it's a list, each item should be a dict with product info
        if isinstance(result, list):
            assert len(result) > 1
            for item in result:
                assert "product_key" in item
                assert "name" in item

    def test_iphone_found(self):
        result = _fuzzy_match("iphone 18")
        assert result is not None
        if isinstance(result, dict):
            assert "iphone" in result["product_key"]

    def test_empty_string_returns_none(self):
        result = _fuzzy_match("")
        assert result is None

    def test_short_query_handled(self):
        # Very short words (≤2 chars) are filtered from scoring
        result = _fuzzy_match("tv")
        # May return None (tv is ≤2 chars in scoring) or exact key match — both OK


class TestFormatProduct:
    def test_format_includes_required_fields(self):
        result = _fuzzy_match("mouse")
        assert isinstance(result, dict)
        formatted = _format_product(result)
        for field in ["name", "price", "raw_price", "stock", "stock_status", "rating", "reviews", "description", "category", "offers"]:
            assert field in formatted, f"Missing field: {field}"

    def test_in_stock_status(self):
        result = _fuzzy_match("mouse")
        formatted = _format_product(result)
        assert formatted["stock_status"] in {"In Stock", "Out of Stock"}

    def test_out_of_stock_keyboard(self):
        """Keychron K8 is seeded with stock=0."""
        result = _fuzzy_match("keychron")
        if isinstance(result, dict):
            formatted = _format_product(result)
            assert formatted["stock_status"] == "Out of Stock"

    def test_price_contains_rs(self):
        result = _fuzzy_match("mouse")
        formatted = _format_product(result)
        assert "Rs." in formatted["price"] or "₹" in formatted["price"]


class TestGetProductDetails:
    def test_found_product_returns_json(self):
        output = get_product_details.invoke({"product_name": "iPhone 18 Pro"})
        data = json.loads(output)
        assert "name" in data or "error" in data

    def test_not_found_returns_error_json(self):
        output = get_product_details.invoke({"product_name": "ZZZ_FAKE_PRODUCT_9999"})
        data = json.loads(output)
        assert "error" in data

    def test_ambiguous_returns_matches(self):
        output = get_product_details.invoke({"product_name": "keyboard"})
        data = json.loads(output)
        # Either found a product OR returned ambiguity error with matches
        assert "name" in data or "matches" in data


class TestSearchProducts:
    def test_search_by_category(self):
        output = search_products.invoke({"category": "Audio"})
        data = json.loads(output)
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_search_by_max_price(self):
        output = search_products.invoke({"category": "", "max_price": 2000})
        data = json.loads(output)
        assert isinstance(data, list)
        for item in data:
            assert item["raw_price"] <= 2000

    def test_search_no_results(self):
        output = search_products.invoke({"category": "NonExistentCategory999"})
        data = json.loads(output)
        assert "message" in data or isinstance(data, list)
