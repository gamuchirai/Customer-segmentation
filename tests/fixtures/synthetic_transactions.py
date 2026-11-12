"""Synthetic retail transaction fixtures for testing data models and contracts."""

from __future__ import annotations

from typing import Any

# Representative synthetic transactions covering valid sales, unidentified guests,
# cancellations, non-merchandise codes, duplicates, and wholesale buyers.
SAMPLE_RAW_TRANSACTIONS: list[dict[str, Any]] = [
    # 1. Valid customer order (UK consumer)
    {
        "source_sheet": "Year 2009-2010",
        "source_row_num": 2,
        "loaded_at": "2026-11-12T00:00:00",
        "invoice": "489434",
        "stock_code": "85048",
        "description": "15CM CHRISTMAS GLASS BALL 20 LIGHTS",
        "quantity": 12,
        "invoice_date": "2009-12-01 07:45:00",
        "price": 6.95,
        "customer_id": "13085",
        "country": "United Kingdom",
    },
    # 2. Second line on same invoice (mixed casing on stock_code)
    {
        "source_sheet": "Year 2009-2010",
        "source_row_num": 3,
        "loaded_at": "2026-11-12T00:00:00",
        "invoice": "489434",
        "stock_code": "79323p",
        "description": "PINK CHERRY BLOSSOM LIGHTS",
        "quantity": 8,
        "invoice_date": "2009-12-01 07:45:00",
        "price": 6.75,
        "customer_id": "13085",
        "country": "United Kingdom",
    },
    # 3. Valid order without customer ID (unidentified guest)
    {
        "source_sheet": "Year 2009-2010",
        "source_row_num": 4,
        "loaded_at": "2026-11-12T00:00:00",
        "invoice": "489435",
        "stock_code": "22350",
        "description": "CAT BOWL",
        "quantity": 4,
        "invoice_date": "2009-12-01 08:00:00",
        "price": 2.55,
        "customer_id": None,
        "country": "France",
    },
    # 4. Wholesale high volume purchase
    {
        "source_sheet": "Year 2009-2010",
        "source_row_num": 5,
        "loaded_at": "2026-11-12T00:00:00",
        "invoice": "489436",
        "stock_code": "85048",
        "description": "15CM CHRISTMAS GLASS BALL 20 LIGHTS",
        "quantity": 500,
        "invoice_date": "2009-12-01 09:15:00",
        "price": 25.0,
        "customer_id": "18102",
        "country": "United Kingdom",
    },
    # 5. Cancellation line (invoice starts with C, negative quantity)
    {
        "source_sheet": "Year 2009-2010",
        "source_row_num": 6,
        "loaded_at": "2026-11-12T00:00:00",
        "invoice": "C489437",
        "stock_code": "85048",
        "description": "15CM CHRISTMAS GLASS BALL 20 LIGHTS",
        "quantity": -12,
        "invoice_date": "2009-12-01 09:30:00",
        "price": 6.95,
        "customer_id": "13085",
        "country": "United Kingdom",
    },
    # 6. Non-merchandise postal charge line
    {
        "source_sheet": "Year 2009-2010",
        "source_row_num": 7,
        "loaded_at": "2026-11-12T00:00:00",
        "invoice": "489438",
        "stock_code": "POST",
        "description": "POSTAGE",
        "quantity": 1,
        "invoice_date": "2009-12-01 10:00:00",
        "price": 18.0,
        "customer_id": "13085",
        "country": "United Kingdom",
    },
    # 7. Non-merchandise manual fee line
    {
        "source_sheet": "Year 2009-2010",
        "source_row_num": 8,
        "loaded_at": "2026-11-12T00:00:00",
        "invoice": "489439",
        "stock_code": "M",
        "description": "Manual",
        "quantity": 1,
        "invoice_date": "2009-12-01 10:15:00",
        "price": 5.0,
        "customer_id": "13085",
        "country": "United Kingdom",
    },
    # 8. Zero price adjustment row
    {
        "source_sheet": "Year 2009-2010",
        "source_row_num": 9,
        "loaded_at": "2026-11-12T00:00:00",
        "invoice": "489440",
        "stock_code": "22350",
        "description": "damaged",
        "quantity": -5,
        "invoice_date": "2009-12-01 10:30:00",
        "price": 0.0,
        "customer_id": None,
        "country": "United Kingdom",
    },
    # 9. Cross-sheet exact duplicate of row 1 appearing in Year 2010-2011
    {
        "source_sheet": "Year 2010-2011",
        "source_row_num": 2,
        "loaded_at": "2026-11-12T00:00:00",
        "invoice": "489434",
        "stock_code": "85048",
        "description": "15CM CHRISTMAS GLASS BALL 20 LIGHTS",
        "quantity": 12,
        "invoice_date": "2009-12-01 07:45:00",
        "price": 6.95,
        "customer_id": "13085",
        "country": "United Kingdom",
    },
]
