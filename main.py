from fastapi import FastAPI
import requests
import re

app = FastAPI()

VALID_EVENTS = ["order.created"]
VALID_STATUS = ["paid","pending","refunded"]

EMAIL_REGEX = r'^[^@]+@[^@]+\.[^@]+$'


@app.get("/")
def health():
    return {"status":"ok"}


@app.post("/process")
def process(order: dict):

    errors = []

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
        errors.append("invalid email")

    if order.get("status") not in VALID_STATUS:
        errors.append("invalid status")

    enriched_lines = []

    revenue_original = 0

    for line in order.get("lines",[]):

        pid = line.get("product_id")

        qty = line.get("quantity")

        if not isinstance(qty,int):
            errors.append(
                f"invalid quantity for product {pid}"
            )
            continue

        if pid < 1 or pid > 100:
            errors.append(
                f"invalid product_id {pid}"
            )
            continue

        catalog = requests.get(
            f"https://dummyjson.com/products/{pid}",
            timeout=10
        )

        if catalog.status_code != 200:
            errors.append(
                f"catalog lookup failed for {pid}"
            )
            continue

        product = catalog.json()

        subtotal = qty * float(
            line["unit_price"]
        )

        revenue_original += subtotal

        enriched_lines.append({
            "product_id": pid,
            "product_name": product["title"],
            "category": product["category"],
            "catalog_price": product["price"],
            "quantity": qty,
            "line_total": subtotal
        })

    if errors:
        return {
            "valid":False,
            "reasons":errors
        }

    currency = order["currency"]

    fx = requests.get(
        "https://api.frankfurter.dev/v1/latest?base=USD",
        timeout=10
    ).json()

    if currency == "USD":
        fx_rate = 1
    else:
        fx_rate = fx["rates"][currency]

    revenue_usd = revenue_original / fx_rate

    return {
        "valid":True,
        "order_id":order["order_id"],
        "fx_rate_used":fx_rate,
        "revenue_usd":round(
            revenue_usd,
            2
        ),
        "lines":enriched_lines
    }
