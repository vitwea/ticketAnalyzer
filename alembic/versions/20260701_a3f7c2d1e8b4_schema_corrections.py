"""Schema corrections from ticketAnalyzer code audit.

Applied changes:
  1. receipt.datetime  → receipt.purchased_at  (column rename, M-3)
  2. source.name       → UNIQUE constraint      (M-7 / race-condition fix)
  3. receipt_line.unit → CHECK constraint       (M-7, rejects unexpected OCR values)
  4. product           → composite index        (H-4, speeds up get_or_create_product)
  5. product_alias     → index on original_name (H-4, speeds up alias lookups)
  6. receipt_line      → index on id_receipt    (H-4, speeds up receipt assembly)

How to apply
────────────
Existing installation (has DB with the old schema):
    alembic upgrade head

Fresh installation (tables created by create_all_tables.py):
    python -m src.db.create_tables      # creates tables with the current schema
    alembic stamp head                  # marks DB as already at this revision

Revision ID: a3f7c2d1e8b4
Revises:
Create Date: 2026-07-01
"""

from __future__ import annotations

from alembic import op


# revision identifiers used by Alembic
revision = "a3f7c2d1e8b4"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Rename receipt.datetime → purchased_at ─────────────────────────
    # batch_alter_table works on both PostgreSQL (ALTER COLUMN) and SQLite
    # (table recreation), so no dialect branching is needed.
    with op.batch_alter_table("receipt") as batch_op:
        batch_op.alter_column("datetime", new_column_name="purchased_at")

    # ── 2. UNIQUE constraint on source.name ───────────────────────────────
    # Source names form a small fixed vocabulary ("Email", "WhatsApp", …).
    # Without this constraint, concurrent inserts can create duplicate rows.
    with op.batch_alter_table("source") as batch_op:
        batch_op.create_unique_constraint("uq_source_name", ["name"])

    # ── 3. CHECK constraint on receipt_line.unit ──────────────────────────
    # Rejects unexpected OCR output before it reaches the DB.
    # Extend the IN list (and create a new migration) when new units appear.
    with op.batch_alter_table("receipt_line") as batch_op:
        batch_op.create_check_constraint(
            "ck_receipt_line_unit",
            "unit IN ('unidad', 'kg', 'litro', 'g', 'ml', 'pack')",
        )

    # ── 4–6. Indexes ──────────────────────────────────────────────────────
    # These run outside batch_alter_table — CREATE INDEX works identically
    # on PostgreSQL and SQLite and doesn't require table recreation.
    op.create_index(
        "ix_product_name_cat_brand",
        "product",
        ["normalized_name", "id_category", "id_brand"],
    )
    op.create_index(
        "ix_alias_original_name",
        "product_alias",
        ["original_name"],
    )
    op.create_index(
        "ix_receipt_line_receipt",
        "receipt_line",
        ["id_receipt"],
    )


def downgrade() -> None:
    # ── Indexes ───────────────────────────────────────────────────────────
    op.drop_index("ix_receipt_line_receipt",    table_name="receipt_line")
    op.drop_index("ix_alias_original_name",     table_name="product_alias")
    op.drop_index("ix_product_name_cat_brand",  table_name="product")

    # ── CHECK constraint ──────────────────────────────────────────────────
    with op.batch_alter_table("receipt_line") as batch_op:
        batch_op.drop_constraint("ck_receipt_line_unit", type_="check")

    # ── UNIQUE constraint ─────────────────────────────────────────────────
    with op.batch_alter_table("source") as batch_op:
        batch_op.drop_constraint("uq_source_name", type_="unique")

    # ── Column rename ─────────────────────────────────────────────────────
    with op.batch_alter_table("receipt") as batch_op:
        batch_op.alter_column("purchased_at", new_column_name="datetime")