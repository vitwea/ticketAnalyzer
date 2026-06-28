"""
src/ocr/examples.py

Builds the few-shot examples block injected into the Gemini prompt.

Two sources (merged and deduplicated by original_name):
  1. examples.json  — curated manual examples for known edge cases
  2. PostgreSQL DB  — product_alias JOIN product JOIN category, built
                      automatically from every processed ticket

The result is a compact JSON array injected at the end of _PROMPT so
Gemini can learn from real tickets without changing the rule definitions.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.config.logger import get_logger

logger = get_logger(__name__)

_EXAMPLES_PATH = Path(__file__).parent / "examples.json"
_DB_LIMIT = 200  # max examples pulled from DB per call


def _load_manual_examples() -> list[dict]:
    """Load curated examples from examples.json."""
    try:
        with open(_EXAMPLES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("examples", [])
    except Exception as e:
        logger.warning(f"Could not load examples.json: {e}")
        return []


def _load_db_examples() -> list[dict]:
    """
    Pull learned examples from the database.
    Returns product_alias rows joined with product name, category and brand.
    Only includes aliases where original_name != normalized_name (real aliases).
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
                .join(Product, ProductAlias.id_product == Product.id_product)
                .join(Category, Product.id_category == Category.id_category)
                .outerjoin(Brand, Product.id_brand == Brand.id_brand)
                .order_by(ProductAlias.id_alias.desc())
                .limit(_DB_LIMIT)
                .all()
            )
            return [
                {
                    "original_name": r.original_name,
                    "name": r.normalized_name,
                    "category": r.category,
                    "brand": r.brand,
                }
                for r in rows
            ]
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Could not load DB examples: {e}")
        return []


def build_examples_block() -> str:
    """
    Merge manual + DB examples, deduplicate by original_name,
    and return a formatted string ready to append to the prompt.
    """
    manual = _load_manual_examples()
    db     = _load_db_examples()

    # Manual examples take priority — deduplicate DB by original_name
    manual_keys = {e["original_name"].upper() for e in manual}
    db_filtered = [e for e in db if e["original_name"].upper() not in manual_keys]

    all_examples = manual + db_filtered

    if not all_examples:
        return ""

    # Build compact representation for the prompt
    lines = []
    for e in all_examples:
        brand_str = f'"{e["brand"]}"' if e.get("brand") else "null"
        note = f'  # {e["note"]}' if e.get("note") else ""
        lines.append(
            f'  {{"original_name": "{e["original_name"]}", '
            f'"name": "{e["name"]}", '
            f'"category": "{e["category"]}", '
            f'"brand": {brand_str}}}{note}'
        )

    block = (
        "\n════════════════════════════════════════════════════════════\n"
        "EJEMPLOS REALES (usa estos como referencia para casos similares)\n"
        "════════════════════════════════════════════════════════════\n"
        "[\n"
        + "\n".join(lines)
        + "\n]"
    )
    return block