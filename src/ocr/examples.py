"""
src/ocr/examples.py

Builds the few-shot examples block injected into the Gemini prompt.

Two sources (merged and deduplicated by original_name):
  1. examples.json  — curated manual examples for known edge cases
  2. PostgreSQL DB  — product_alias rows joined with product/category/brand,
                      built automatically from every processed ticket

Performance note (M-4):
  build_examples_block() is called on every OCR invocation.  The DB query
  is cheap but unnecessary to repeat at sub-second intervals.  Results are
  cached in-process for _CACHE_TTL_SECONDS (default 5 min).  The cache is
  intentionally process-scoped — no Redis/Memcached needed at this scale.
  Call invalidate_examples_cache() after committing new aliases if you need
  the next OCR call to pick them up immediately.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from src.config.logger import get_logger

logger = get_logger(__name__)

_EXAMPLES_PATH = Path(__file__).parent / "examples.json"
_DB_LIMIT        = 200   # max examples pulled from DB per cache fill
_CACHE_TTL_SECONDS = 300  # 5 minutes


# ── Cache state ──────────────────────────────────────────────────────────────

_cache_ts: float = 0.0
_cache_block: str = ""


def invalidate_examples_cache() -> None:
    """Force the next build_examples_block() call to re-query the database."""
    global _cache_ts
    _cache_ts = 0.0


# ── Internal helpers ─────────────────────────────────────────────────────────

def _load_manual_examples() -> list[dict]:
    """Load curated examples from examples.json."""
    try:
        with open(_EXAMPLES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("examples", [])
    except Exception as e:
        logger.warning("Could not load examples.json: %s", e)
        return []


def _load_db_examples() -> list[dict]:
    """
    Pull learned examples from the database.
    Returns product_alias rows joined with product name, category and brand.
    """
    try:
        from src.db.connection import SessionLocal
        from src.db.models import ProductAlias, Product, Category, Brand

        db = SessionLocal()
        try:
            rows = (
                db.query(
                    ProductAlias.original_name,
                    Product.normalized_name,
                    Category.name.label("category"),
                    Brand.name.label("brand"),
                )
                .join(Product,   ProductAlias.id_product == Product.id_product)
                .join(Category,  Product.id_category     == Category.id_category)
                .outerjoin(Brand, Product.id_brand        == Brand.id_brand)
                .order_by(ProductAlias.id_alias.desc())
                .limit(_DB_LIMIT)
                .all()
            )
            return [
                {
                    "original_name": r.original_name,
                    "name":          r.normalized_name,
                    "category":      r.category,
                    "brand":         r.brand,
                }
                for r in rows
            ]
        finally:
            db.close()
    except Exception as e:
        logger.warning("Could not load DB examples: %s", e)
        return []


def _compute_examples_block() -> str:
    """Merge manual + DB examples and render the prompt block."""
    manual = _load_manual_examples()
    db_ex  = _load_db_examples()

    manual_keys = {e["original_name"].upper() for e in manual}
    db_filtered = [e for e in db_ex if e["original_name"].upper() not in manual_keys]
    all_examples = manual + db_filtered

    if not all_examples:
        return ""

    lines = []
    for e in all_examples:
        brand_str = f'"{e["brand"]}"' if e.get("brand") else "null"
        note      = f"  # {e['note']}" if e.get("note") else ""
        lines.append(
            f'  {{"original_name": "{e["original_name"]}", '
            f'"name": "{e["name"]}", '
            f'"category": "{e["category"]}", '
            f'"brand": {brand_str}}}{note}'
        )

    return (
        "\n════════════════════════════════════════════════════════════\n"
        "EJEMPLOS REALES (usa estos como referencia para casos similares)\n"
        "════════════════════════════════════════════════════════════\n"
        "[\n"
        + "\n".join(lines)
        + "\n]"
    )


# ── Public API ────────────────────────────────────────────────────────────────

def build_examples_block() -> str:
    """
    Return the examples prompt block, using a cached version if available.

    The cache is valid for _CACHE_TTL_SECONDS.  It is invalidated:
      - automatically when the TTL expires
      - explicitly via invalidate_examples_cache()
    """
    global _cache_ts, _cache_block

    if time.monotonic() - _cache_ts < _CACHE_TTL_SECONDS:
        logger.debug("examples: serving from cache (age=%.0fs)", time.monotonic() - _cache_ts)
        return _cache_block

    logger.debug("examples: cache miss — recomputing")
    _cache_block = _compute_examples_block()
    _cache_ts    = time.monotonic()
    return _cache_block