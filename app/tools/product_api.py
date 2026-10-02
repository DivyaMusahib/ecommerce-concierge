"""
Product Catalog API - backed by SQLite via app/database/db.py.

Uses a multi-strategy scored fuzzy match for robust search.

_fuzzy_match scoring (ALL strategies run, best score wins or ambiguous if tied):
  - Exact product_key match             → 100 pts
  - Query fully contained in name       → 50 pts
  - Query word in product_key           → 8 pts/word
  - Query word in product name          → 6 pts/word
  - Query word in synonyms              → 2 pts/word  (WEAKEST — prevents false positives)

Returns:
  - dict   → single unambiguous match
  - list   → 2+ products with similar top scores (ask user to clarify)
  - None   → nothing scored above minimum threshold
"""
import json
from langchain_core.tools import tool
from app.database.db import get_conn

# Score gap threshold — if top 2 candidates are within this many points, it's ambiguous
_AMBIGUITY_THRESHOLD = 6

# Minimum total score to be considered a real match (prevents junk synonym hits)
_MIN_SCORE = 4


def _fuzzy_match(query: str) -> dict | list | None:
    """
    Find a product using a fully-scored multi-strategy search.

    KEY FIX: When a product's key exactly matches the query (e.g. key='iphone',
    query='iphone'), we also look for SIBLING products whose key starts with the
    same prefix (e.g. 'iphone18pro', 'iphone18promax', 'iphoneduo'). If siblings
    exist, all of them are returned as AMBIGUOUS — the user must pick.

    Returns:
      - dict  → single unambiguous match
      - list  → multiple equally-scored matches (ambiguous; caller must ask user)
      - None  → no match above minimum threshold
    """
    q = query.lower().strip()
    if not q:
        return None

    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM products").fetchall()

    rows_as_dicts = [dict(r) for r in rows]

    # ── Step 1: Check for exact key match and collect its "family" ───────────
    # A "family" is: the exact match + any product whose key starts with query
    # AND belongs to the SAME CATEGORY as the exact match.
    # This correctly groups:
    #   iphone + iphone18pro + iphone18promax + iphoneduo (all Smartphone)
    #   headphones + headphones_bose (both Audio)
    #   mouse + mouse_razer (both Peripherals)
    # And correctly EXCLUDES:
    #   laptop_sleeve (Accessories) from being grouped with laptop (Laptop)
    exact_match = None
    sibling_candidates = []
    for row in rows_as_dicts:
        key = row["product_key"].lower()
        if key == q:
            exact_match = row
        elif key.startswith(q) and key != q:
            sibling_candidates.append(row)

    if exact_match is not None:
        # Only include siblings that are in the SAME category
        same_cat_siblings = [r for r in sibling_candidates if r["category"] == exact_match["category"]]
        if same_cat_siblings:
            # Multiple products in the same family → AMBIGUOUS
            return [exact_match] + same_cat_siblings
        # Only one product with this key, no same-category siblings → unambiguous
        return exact_match

    # ── Step 2: Check for query fully contained in product name ─────────────
    # e.g. query='Dell XPS 15' → name contains it → strong match
    # Also collect all name-containment matches to check for ambiguity
    name_matches = [r for r in rows_as_dicts if q in r["name"].lower()]
    if len(name_matches) == 1:
        return name_matches[0]
    if len(name_matches) > 1:
        return name_matches  # Ambiguous name match

    # ── Step 3: Scored word-level matching ──────────────────────────────────
    # Query words — filter out 1-letter stop-words to preserve numbers and short brands
    words = [w for w in q.split() if len(w) > 1]
    if not words:
        words = [q]

    scores: list[tuple[int, dict]] = []

    for row in rows_as_dicts:
        key = row["product_key"].lower()
        name = row["name"].lower()
        synonyms = (row["synonyms"] or "").lower()
        score = 0

        for word in words:
            # Name match: strong signal (check first to prioritize visible names over internal keys)
            if word in name:
                score += 6
            # Key match: moderate signal (avoids substring issues like '18pro' beating '17 pro')
            elif word in key:
                score += 4
            # Synonym match: weak signal (only confirms, not determines)
            elif word in synonyms:
                score += 2

        if score >= _MIN_SCORE:
            scores.append((score, row))

    if not scores:
        return None

    # Sort descending by score
    scores.sort(key=lambda x: x[0], reverse=True)
    top_score = scores[0][0]

    # Collect all candidates within _AMBIGUITY_THRESHOLD of the top score
    top_matches = [r for s, r in scores if top_score - s < _AMBIGUITY_THRESHOLD]

    if len(top_matches) == 1:
        return top_matches[0]

    # Multiple equally-scored candidates → ambiguous, caller must ask user
    return top_matches



def _format_product(row: dict) -> dict:
    offers = []
    try:
        offers = json.loads(row.get("offers_json", "[]"))
    except Exception:
        pass
    return {
        "name": row["name"],
        "price": f"Rs.{row['price']}",
        "raw_price": row["price"],
        "stock": row["stock"],
        "stock_status": "In Stock" if row["stock"] > 0 else "Out of Stock",
        "rating": row["rating"],
        "reviews": row["reviews"],
        "description": row["description"],
        "category": row["category"],
        "offers": offers,
    }


@tool
def get_product_details(product_name: str) -> str:
    """
    Search the product catalog by name or description. Returns price, stock,
    rating, description, and available offers. Handles typos and synonyms.
    e.g. 'phones', 'apple phone', 'noise cancelling headset', 'gaming laptop'.
    """
    result = _fuzzy_match(product_name)

    if result is None:
        return json.dumps({
            "error": f"No product found matching '{product_name}'.",
            "suggestion": "Try: laptop, macbook, iphone, samsung, mouse, keyboard, headphones, or monitor",
        })

    # Ambiguous: return list of candidates for the agent to clarify
    if isinstance(result, list):
        return json.dumps({
            "error": "Ambiguous product name",
            "message": f"Multiple products match '{product_name}'. Please clarify which one you mean.",
            "matches": [{"name": r["name"], "category": r["category"], "price": f"Rs.{r['price']}"} for r in result],
        })

    return json.dumps(_format_product(result))


@tool
def search_products(category: str = "", max_price: int = 0, keyword: str = "") -> str:
    """
    Search products by category, keyword, and/or maximum price (in INR).
    Returns a list of matching products with name, price, rating, and availability.
    
    Parameters:
    - category: Filter by product category. Examples: Smartphone, Laptop, Audio, Peripherals,
      Monitors, Tablet, Gaming, Wearables, Smart Home, Storage, Accessories, Networking,
      Cameras, E-Reader, Television. Leave empty to search all categories.
    - max_price: Maximum price in INR (0 = no limit).
    - keyword: Search term to match against product name or synonyms (e.g. "iphone", "gaming mouse").
    
    Use this when the user asks about a product FAMILY (e.g. "all iPhones", "gaming laptops",
    "headphones under 5000") rather than a specific product name.
    """
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM products").fetchall()

    kw = keyword.lower().strip()
    results = []
    for row in rows:
        if category and category.lower() not in row["category"].lower():
            continue
        if max_price > 0 and row["price"] > max_price:
            continue
        if kw:
            name_match = kw in row["name"].lower()
            key_match = kw in row["product_key"].lower()
            syn_match = kw in (row["synonyms"] or "").lower()
            if not (name_match or key_match or syn_match):
                continue
        results.append({
            "name": row["name"],
            "price": f"₹{row['price']:,}",
            "raw_price": row["price"],
            "rating": row["rating"],
            "stock_status": "In Stock" if row["stock"] > 0 else "Out of Stock",
            "category": row["category"],
        })

    if not results:
        with get_conn() as conn:
            cats = sorted(set(r["category"] for r in conn.execute("SELECT DISTINCT category FROM products").fetchall()))
        return json.dumps({"message": "No products match your criteria.", "available_categories": cats,
                           "tip": "Try a broader category or remove the keyword filter."})
    return json.dumps(results)


@tool
def compare_products(product1_name: str, product2_name: str) -> str:
    """
    Compare two products side-by-side: specs, price, rating, stock, offers.
    Use this instead of calling get_product_details twice.
    """
    r1 = _fuzzy_match(product1_name)
    r2 = _fuzzy_match(product2_name)

    # Handle ambiguous results for compare as well
    if isinstance(r1, list):
        return json.dumps({"error": f"Ambiguous product '{product1_name}'.",
                           "matches": [r["name"] for r in r1]})
    if isinstance(r2, list):
        return json.dumps({"error": f"Ambiguous product '{product2_name}'.",
                           "matches": [r["name"] for r in r2]})

    if not r1:
        return json.dumps({"error": f"Product '{product1_name}' not found."})
    if not r2:
        return json.dumps({"error": f"Product '{product2_name}' not found."})

    p1, p2 = _format_product(r1), _format_product(r2)

    def _winner(attr):
        v1, v2 = p1.get(attr), p2.get(attr)
        if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
            if attr == "raw_price":
                return p1["name"] if v1 < v2 else (p2["name"] if v2 < v1 else "Tie")
            return p1["name"] if v1 > v2 else (p2["name"] if v2 > v1 else "Tie")
        return "N/A"

    return json.dumps({
        "comparison": {
            p1["name"]: {k: v for k, v in p1.items()},
            p2["name"]: {k: v for k, v in p2.items()},
        },
        "verdict": {
            "better_price": _winner("raw_price"),
            "better_rating": _winner("rating"),
            "more_reviews": _winner("reviews"),
        },
    })
