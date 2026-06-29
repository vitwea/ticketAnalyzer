"""
scripts/review_aliases.py

Interactive CLI to review product aliases learned automatically from
processed tickets. Lets you approve them (they become trusted examples)
or correct them (fixes the DB and adds the correction to examples.json).

Usage:
    python -m scripts.review_aliases
    python -m scripts.review_aliases --since 2026-06-01
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from src.db.connection import SessionLocal
from src.db.models import ProductAlias, Product, Category, Brand
from src.config.logger import get_logger

logger = get_logger(__name__)

EXAMPLES_PATH = Path("src/ocr/examples.json")

# ANSI colors
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

CATEGORIES = [
    "Lácteos", "Carnes", "Pescados", "Frutas", "Verduras",
    "Panadería y pastelería", "Bebidas", "Café e infusiones",
    "Droguería", "Higiene", "Congelados", "Snacks",
    "Dulces y repostería", "Huevos", "Cereales y pasta", "Legumbres",
    "Aceites y grasas", "Salsas y conservas", "Platos preparados",
    "Especias y condimentos", "Parafarmacia", "Mascotas", "Otros",
]


# ─────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────

def fetch_aliases() -> list[dict]:
    """Return all aliases with their current product/category/brand."""
    db = SessionLocal()
    try:
        rows = (
            db.query(
                ProductAlias.id_alias,
                ProductAlias.original_name,
                Product.id_product,
                Product.normalized_name,
                Category.name.label("category"),
                Brand.name.label("brand"),
            )
            .join(Product, ProductAlias.id_product == Product.id_product)
            .join(Category, Product.id_category == Category.id_category)
            .outerjoin(Brand, Product.id_brand == Brand.id_brand)
            .order_by(ProductAlias.id_alias.asc())
            .all()
        )
        return [
            {
                "id_alias":      r.id_alias,
                "id_product":    r.id_product,
                "original_name": r.original_name,
                "name":          r.normalized_name,
                "category":      r.category,
                "brand":         r.brand,
            }
            for r in rows
        ]
    finally:
        db.close()


def count_product_usages(id_product: int) -> int:
    """Return how many aliases and receipt_lines share this product row."""
    from src.db.models import ReceiptLine
    db = SessionLocal()
    try:
        alias_count = db.query(ProductAlias).filter_by(id_product=id_product).count()
        line_count  = db.query(ReceiptLine).filter_by(id_product=id_product).count()
        return alias_count + line_count
    finally:
        db.close()


def update_alias_in_db(alias: dict, new_name: str, new_category: str,
                       new_brand: str | None) -> None:
    """
    Safely update a product alias correction.

    If the product row is shared (used by other aliases or receipt_lines),
    creates a NEW product row instead of mutating the existing one, so
    other aliases/lines are not affected.
    """
    db = SessionLocal()
    try:
        usages = count_product_usages(alias["id_product"])
        shared = usages > 1  # more than just this alias

        # Resolve or create category
        category = db.query(Category).filter_by(name=new_category).first()
        if not category:
            category = Category(name=new_category)
            db.add(category)
            db.flush()

        # Resolve or create brand
        id_brand = None
        if new_brand:
            brand = db.query(Brand).filter_by(name=new_brand).first()
            if not brand:
                brand = Brand(name=new_brand)
                db.add(brand)
                db.flush()
            id_brand = brand.id_brand

        if shared:
            # Create a new product row — don't touch the shared one
            new_product = Product(
                normalized_name=new_name,
                id_category=category.id_category,
                id_brand=id_brand,
            )
            db.add(new_product)
            db.flush()

            # Re-point only THIS alias to the new product
            alias_row = db.query(ProductAlias).filter_by(
                id_alias=alias["id_alias"]
            ).first()
            alias_row.id_product = new_product.id_product

            print(f"{YELLOW}  Product was shared ({usages} usages) → "
                  f"created new product row (id={new_product.id_product}).{RESET}")
        else:
            # Safe to update the existing product in place
            product = db.query(Product).filter_by(
                id_product=alias["id_product"]
            ).first()
            product.normalized_name = new_name
            product.id_category     = category.id_category
            product.id_brand        = id_brand

        db.commit()
        print(f"{GREEN}  ✓ DB updated.{RESET}")
    except Exception as e:
        db.rollback()
        print(f"{RED}  Error updating DB: {e}{RESET}")
        raise
    finally:
        db.close()


# ─────────────────────────────────────────────
# examples.json helpers
# ─────────────────────────────────────────────

def load_examples() -> dict:
    if EXAMPLES_PATH.exists():
        with open(EXAMPLES_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"examples": []}


def save_examples(data: dict) -> None:
    with open(EXAMPLES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_to_examples(entry: dict, data: dict) -> None:
    """Add or update an entry in examples.json keyed by original_name."""
    examples = data.setdefault("examples", [])
    existing = next(
        (e for e in examples
         if e["original_name"].upper() == entry["original_name"].upper()),
        None,
    )
    if existing:
        existing.update(entry)
        print(f"{GREEN}  ✓ Updated in examples.json.{RESET}")
    else:
        examples.append(entry)
        print(f"{GREEN}  ✓ Added to examples.json.{RESET}")


def already_in_examples(original_name: str, data: dict) -> bool:
    return any(
        e["original_name"].upper() == original_name.upper()
        for e in data.get("examples", [])
    )


# ─────────────────────────────────────────────
# UI helpers
# ─────────────────────────────────────────────

def pick_category(current: str) -> str:
    print(f"\n  {BOLD}Available categories:{RESET}")
    for i, cat in enumerate(CATEGORIES, 1):
        marker = f"{GREEN}← current{RESET}" if cat == current else ""
        print(f"    {i:2}. {cat} {marker}")
    while True:
        raw = input(f"  Enter number (or Enter to keep '{current}'): ").strip()
        if not raw:
            return current
        if raw.isdigit() and 1 <= int(raw) <= len(CATEGORIES):
            return CATEGORIES[int(raw) - 1]
        print(f"  {RED}Invalid choice.{RESET}")


def _print_summary(approved: int, corrected: int,
                   discarded: int, skipped: int) -> None:
    print(f"\n{BOLD}═══════════════════════════════════════════{RESET}")
    print(f"  {GREEN}Approved : {approved}{RESET}")
    print(f"  {YELLOW}Corrected: {corrected}{RESET}")
    print(f"  {RED}Discarded: {discarded}{RESET}")
    print(f"  {CYAN}Skipped  : {skipped}{RESET}")
    print(f"{BOLD}═══════════════════════════════════════════{RESET}\n")


# ─────────────────────────────────────────────
# Main review loop
# ─────────────────────────────────────────────

def review(since: datetime | None = None) -> None:
    aliases  = fetch_aliases()
    examples = load_examples()

    pending = [
        a for a in aliases
        if not already_in_examples(a["original_name"], examples)
    ]

    if not pending:
        print(f"{GREEN}Nothing to review — all aliases are in examples.json.{RESET}")
        return

    print(f"\n{BOLD}{CYAN}═══════════════════════════════════════════{RESET}")
    print(f"{BOLD}{CYAN}  ticketAnalyzer — alias review{RESET}")
    print(f"{BOLD}{CYAN}═══════════════════════════════════════════{RESET}")
    print(f"  {len(pending)} aliases to review\n")
    print(f"  {GREEN}y{RESET}=approve  {YELLOW}e{RESET}=edit  "
          f"{RED}d{RESET}=discard  {CYAN}s{RESET}=skip  {BOLD}q{RESET}=quit\n")

    approved = corrected = discarded = skipped = 0

    for i, alias in enumerate(pending, 1):
        brand_str = alias["brand"] or "null"
        print(f"{BOLD}[{i}/{len(pending)}]{RESET}  "
              f"{CYAN}{alias['original_name']}{RESET}")
        print(f"  name     : {alias['name']}")
        print(f"  category : {alias['category']}")
        print(f"  brand    : {brand_str}")

        while True:
            cmd = input("  → ").strip().lower()

            if cmd == "y":
                add_to_examples({
                    "original_name": alias["original_name"],
                    "name":          alias["name"],
                    "category":      alias["category"],
                    "brand":         alias["brand"],
                }, examples)
                save_examples(examples)
                approved += 1
                break

            elif cmd == "e":
                print(f"\n  {YELLOW}Editing — press Enter to keep current value.{RESET}")

                new_name = (
                    input(f"  name [{alias['name']}]: ").strip()
                    or alias["name"]
                )
                new_category = pick_category(alias["category"])
                new_brand_raw = input(
                    f"  brand [{brand_str}] (or 'null'): "
                ).strip()
                new_brand = (
                    None if new_brand_raw.lower() in ("null", "")
                    else new_brand_raw or alias["brand"]
                )

                update_alias_in_db(alias, new_name, new_category, new_brand)
                add_to_examples({
                    "original_name": alias["original_name"],
                    "name":          new_name,
                    "category":      new_category,
                    "brand":         new_brand,
                    "note":          "manually corrected",
                }, examples)
                save_examples(examples)
                corrected += 1
                break

            elif cmd == "d":
                print(f"  {RED}Discarded (not added to examples).{RESET}")
                discarded += 1
                break

            elif cmd == "s":
                print(f"  {CYAN}Skipped.{RESET}")
                skipped += 1
                break

            elif cmd == "q":
                print(f"\n{BOLD}Stopped early.{RESET}")
                _print_summary(approved, corrected, discarded, skipped)
                sys.exit(0)

            else:
                print(f"  {RED}Unknown command. Use y / e / d / s / q{RESET}")

        print()

    _print_summary(approved, corrected, discarded, skipped)


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Review product aliases learned from processed tickets."
    )
    parser.add_argument(
        "--since",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d"),
        help="Only show aliases from tickets after this date (YYYY-MM-DD)",
        default=None,
    )
    args = parser.parse_args()
    review(since=args.since)


if __name__ == "__main__":
    main()