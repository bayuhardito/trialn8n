from fastapi import FastAPI
import requests
import re

app = FastAPI()

VALID_EVENTS = ["order.created"]
VALID_STATUS = ["paid", "pending", "refunded"]

EMAIL_REGEX = r'^[^@]+@[^@]+\.[^@]+$'

PRODUCT_CACHE = {}
FX_CACHE = None


@app.get("/")
def health():
    return {
        "status": "ok"
    }


@app.post("/process")
def process(order: dict):

    errors = []

    # =====================
    # Basic Validation
    # =====================

    if order.get("event") not in VALID_EVENTS:
        errors.append("invalid event")

    if not order.get("order_id"):
        errors.append("missing order_id")

    if not order.get("customer_email"):
        errors.append("missing customer_email")

    elif not re.match(
        EMAIL_REGEX,
        order["customer_email"]
    ):
        errors.append("invalid customer_email")

    if order.get("status") not in VALID_STATUS:
        errors.append("invalid status")

    if not order.get("currency"):
        errors.append("missing currency")

    enriched_lines = []
    revenue_original = 0

    # =====================
    # Product Enrichment
    # =====================

    for line in order.get("lines", []):

        pid = line.get("product_id")
        qty = line.get("quantity")
        unit_price = line.get("unit_price")

        # product_id validation
        if not isinstance(pid, int):
            errors.append(
                f"invalid product_id {pid}"
            )
            continue

        if pid < 1 or pid > 100:
            errors.append(
                f"invalid product_id {pid}"
            )
            continue

        # quantity validation
        if not isinstance(qty, int):
            errors.append(
                f"invalid quantity for product {pid}"
            )
            continue

        if qty <= 0:
            errors.append(
                f"quantity must be > 0 for product {pid}"
            )
            continue

        # unit_price validation
        try:
            unit_price = float(unit_price)
        except:
            errors.append(
                f"invalid unit_price for product {pid}"
            )
            continue

        # Product cache
        if pid not in PRODUCT_CACHE:

            try:
                catalog_response = requests.get(
                    f"https://dummyjson.com/products/{pid}",
                    timeout=10
                )

                if catalog_response.status_code != 200:
                    errors.append(
                        f"catalog lookup failed for {pid}"
                    )
                    continue

                PRODUCT_CACHE[pid] = catalog_response.json()

            except Exception:
                errors.append(
                    f"catalog service unavailable for {pid}"
                )
                continue

        product = PRODUCT_CACHE[pid]

        subtotal = qty * unit_price
        revenue_original += subtotal

        enriched_lines.append({
            "product_id": pid,
            "product_name": product["title"],
            "category": product["category"],
            "catalog_price": product["price"],
            "quantity": qty,
            "line_total": subtotal
        })

    # Return rejected record
    if errors:
        return {
            "valid": False,
            "reasons": errors
        }

    # =====================
    # FX Conversion
    # =====================

    global FX_CACHE

    try:
        if FX_CACHE is None:

            fx_response = requests.get(
                "https://api.frankfurter.dev/v1/latest?base=USD",
                timeout=10
            )

            if fx_response.status_code != 200:
                return {
                    "valid": False,
                    "reasons": [
                        "fx service unavailable"
                    ]
                }

            FX_CACHE = fx_response.json()

        fx = FX_CACHE

    except Exception:
        return {
            "valid": False,
            "reasons": [
                "fx service unavailable"
            ]
        }

    currency = order.get("currency")

    if currency == "USD":
        fx_rate = 1

    elif currency in fx["rates"]:
        fx_rate = fx["rates"][currency]

    else:
        return {
            "valid": False,
            "reasons": [
                f"unsupported currency {currency}"
            ]
        }

    revenue_usd = revenue_original / fx_rate

    # =====================
    # Success Response
    # =====================

    return {
        "valid": True,
        "order_id": order["order_id"],
        "fx_rate_used": fx_rate,
        "revenue_usd": round(
            revenue_usd,
            2
        ),
        "lines": enriched_lines
    }
