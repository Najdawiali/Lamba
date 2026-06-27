"""
CSV Parser utility for product inventory imports.

Validates and transforms CSV rows into product dictionaries
ready for database insertion and Elasticsearch indexing.
"""

import csv
import io
from dataclasses import dataclass


@dataclass
class CSVParseResult:
    """Result of parsing a CSV file."""
    products: list[dict]
    errors: list[str]
    total_rows: int
    valid_rows: int


REQUIRED_COLUMNS = {"name"}
OPTIONAL_COLUMNS = {"description", "price", "category", "in_stock"}
ALL_COLUMNS = REQUIRED_COLUMNS | OPTIONAL_COLUMNS


def parse_product_csv(content: bytes) -> CSVParseResult:
    """
    Parse a CSV file containing product data.

    Expected columns (header row required):
        name*        — Product name (required)
        description  — Product description
        price        — Numeric price
        category     — Product category
        in_stock     — true/false/1/0/yes/no

    Args:
        content: Raw CSV file bytes

    Returns:
        CSVParseResult with parsed products and any errors
    """
    decoded = content.decode("utf-8-sig")  # Handle BOM from Excel
    reader = csv.DictReader(io.StringIO(decoded))

    if reader.fieldnames is None:
        return CSVParseResult(products=[], errors=["Empty CSV file"], total_rows=0, valid_rows=0)

    # Normalize column names
    normalized_fields = {f.strip().lower() for f in reader.fieldnames}

    # Check required columns
    missing = REQUIRED_COLUMNS - normalized_fields
    if missing:
        return CSVParseResult(
            products=[], errors=[f"Missing required columns: {', '.join(missing)}"],
            total_rows=0, valid_rows=0,
        )

    products = []
    errors = []
    total_rows = 0

    for i, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
        total_rows += 1

        # Normalize keys
        row = {k.strip().lower(): v.strip() if v else "" for k, v in row.items()}

        name = row.get("name", "").strip()
        if not name:
            errors.append(f"Row {i}: Missing product name, skipped")
            continue

        # Parse price
        price = None
        price_str = row.get("price", "").strip()
        if price_str:
            try:
                price = float(price_str)
                if price < 0:
                    errors.append(f"Row {i}: Negative price '{price_str}', set to None")
                    price = None
            except ValueError:
                errors.append(f"Row {i}: Invalid price '{price_str}', set to None")

        # Parse in_stock
        in_stock_str = row.get("in_stock", "true").strip().lower()
        in_stock = in_stock_str in ("true", "1", "yes", "")

        products.append({
            "name": name,
            "description": row.get("description", "").strip() or None,
            "price": price,
            "category": row.get("category", "").strip() or None,
            "in_stock": in_stock,
        })

    return CSVParseResult(
        products=products,
        errors=errors,
        total_rows=total_rows,
        valid_rows=len(products),
    )
