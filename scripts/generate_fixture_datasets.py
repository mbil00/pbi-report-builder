#!/usr/bin/env python3
"""Generate deterministic CSV datasets for the real-report fixture specs.

Usage:
    python scripts/generate_fixture_datasets.py
    python scripts/generate_fixture_datasets.py --output fixtures/real-report-fixtures
    python scripts/generate_fixture_datasets.py --dataset kitchen-sink
    python scripts/generate_fixture_datasets.py --dataset desktop-shapes
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import struct
import zlib
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "fixtures" / "real-report-fixtures"


@dataclass(frozen=True)
class ProductRow:
    product_key: int
    sku: str
    product_name: str
    brand: str
    category: str
    subcategory: str
    color: str
    unit_list_price: float
    launch_date: date
    is_active: bool
    unit_cost: float


@dataclass(frozen=True)
class CustomerRow:
    customer_key: int
    customer_name: str
    segment: str
    region: str
    country: str
    city: str
    postal_code: str
    signup_date: date


@dataclass(frozen=True)
class StoreRow:
    store_key: int
    store_name: str
    store_type: str
    region: str
    manager: str
    open_date: date


@dataclass(frozen=True)
class PromotionRow:
    promotion_key: int
    promotion_name: str
    promotion_type: str
    start_date: date
    end_date: date


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Base output directory for generated fixture CSVs.",
    )
    parser.add_argument(
        "--dataset",
        choices=("all", "kitchen-sink", "model-heavy", "desktop-shapes"),
        default="all",
        help="Which fixture dataset to generate.",
    )
    args = parser.parse_args()

    output_root = args.output.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    # Merge into the existing manifest so generating a single dataset keeps
    # the other datasets' entries.
    manifest_path = output_root / "manifest.json"
    manifest: dict[str, dict[str, int | str]] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if args.dataset in ("all", "kitchen-sink"):
        kitchen_dir = output_root / "report-01-kitchen-sink" / "data"
        reset_dir(kitchen_dir)
        manifest["report-01-kitchen-sink"] = generate_kitchen_sink(kitchen_dir)

    if args.dataset in ("all", "model-heavy"):
        model_dir = output_root / "report-02-model-heavy" / "data"
        reset_dir(model_dir)
        manifest["report-02-model-heavy"] = generate_model_heavy(model_dir)

    if args.dataset in ("all", "desktop-shapes"):
        shapes_dir = output_root / "report-04-desktop-shapes" / "data"
        reset_dir(shapes_dir)
        manifest["report-04-desktop-shapes"] = generate_desktop_shapes(shapes_dir)

    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print(f"Wrote fixture datasets to {output_root}")
    for name, info in sorted(manifest.items()):
        row_total = sum(value for key, value in info.items() if key.endswith("_rows"))
        csv_count = sum(1 for key in info if key.endswith("_rows"))
        print(f"  {name}: {row_total} rows across {csv_count} files")


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def stable_int(*parts: object) -> int:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def choose(items: list[str], *parts: object) -> str:
    return items[stable_int(*parts) % len(items)]


def bounded_int(low: int, high: int, *parts: object) -> int:
    return low + (stable_int(*parts) % (high - low + 1))


def bounded_float(low: float, high: float, step: float, *parts: object) -> float:
    units = round((high - low) / step)
    return round(low + (stable_int(*parts) % (units + 1)) * step, 2)


def daterange(start: date, end: date) -> list[date]:
    days = (end - start).days
    return [start + timedelta(days=offset) for offset in range(days + 1)]


def month_starts(start: date, end: date) -> list[date]:
    months: list[date] = []
    current = date(start.year, start.month, 1)
    final = date(end.year, end.month, 1)
    while current <= final:
        months.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return months


def fmt_date(value: date) -> str:
    return value.isoformat()


def write_csv(path: Path, rows: list[dict[str, object]]) -> int:
    if not rows:
        raise ValueError(f"Cannot write empty CSV: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return len(rows)


def generate_kitchen_sink(output_dir: Path) -> dict[str, int | str]:
    start = date(2023, 1, 1)
    end = date(2024, 12, 31)
    all_dates = daterange(start, end)
    months = month_starts(start, end)

    products = kitchen_sink_products()
    customers = kitchen_sink_customers()
    stores = kitchen_sink_stores()
    promotions = kitchen_sink_promotions()
    channels = [
        {"ChannelKey": 1, "ChannelName": "Retail"},
        {"ChannelKey": 2, "ChannelName": "Online"},
        {"ChannelKey": 3, "ChannelName": "Distributor"},
    ]

    date_rows = [
        {
            "Date": fmt_date(day),
            "Year": day.year,
            "Quarter": f"Q{((day.month - 1) // 3) + 1}",
            "MonthNumber": day.month,
            "MonthName": day.strftime("%B"),
            "MonthShort": day.strftime("%b"),
            "YearMonth": day.strftime("%Y-%m"),
            "WeekOfYear": int(day.strftime("%V")),
            "DayOfWeek": day.strftime("%A"),
            "IsWeekend": day.weekday() >= 5,
        }
        for day in all_dates
    ]

    product_rows = [
        {
            "ProductKey": product.product_key,
            "SKU": product.sku,
            "ProductName": product.product_name,
            "Brand": product.brand,
            "Category": product.category,
            "Subcategory": product.subcategory,
            "Color": product.color,
            "UnitListPrice": f"{product.unit_list_price:.2f}",
            "LaunchDate": fmt_date(product.launch_date),
            "IsActive": product.is_active,
        }
        for product in products
    ]

    customer_rows = [
        {
            "CustomerKey": customer.customer_key,
            "CustomerName": customer.customer_name,
            "Segment": customer.segment,
            "Region": customer.region,
            "Country": customer.country,
            "City": customer.city,
            "PostalCode": customer.postal_code,
            "SignupDate": fmt_date(customer.signup_date),
        }
        for customer in customers
    ]

    store_rows = [
        {
            "StoreKey": store.store_key,
            "StoreName": store.store_name,
            "StoreType": store.store_type,
            "Region": store.region,
            "Manager": store.manager,
            "OpenDate": fmt_date(store.open_date),
        }
        for store in stores
    ]

    promotion_rows = [
        {
            "PromotionKey": promo.promotion_key,
            "PromotionName": promo.promotion_name,
            "PromotionType": promo.promotion_type,
            "StartDate": fmt_date(promo.start_date),
            "EndDate": fmt_date(promo.end_date),
        }
        for promo in promotions
    ]

    sales_rows: list[dict[str, object]] = []
    for sales_key in range(1, 1801):
        order_date = all_dates[stable_int("order-date", sales_key) % len(all_dates)]
        ship_days = bounded_int(1, 6, "ship-days", sales_key)
        ship_date = min(order_date + timedelta(days=ship_days), end)
        product = products[stable_int("product", sales_key) % len(products)]
        customer = customers[stable_int("customer", sales_key) % len(customers)]
        store = stores[stable_int("store", sales_key) % len(stores)]
        channel_key = 1 + (stable_int("channel", sales_key) % len(channels))

        promotion_key: int | str = ""
        discount_amount = 0.0
        if stable_int("promotion", sales_key) % 5 != 0:
            promo = promotions[stable_int("promo-key", sales_key) % len(promotions)]
            promotion_key = promo.promotion_key
            discount_rate = {1: 0.05, 2: 0.08, 3: 0.12}[1 + (stable_int("disc", sales_key) % 3)]
        else:
            discount_rate = 0.0

        quantity = bounded_int(1, 8, "qty", sales_key)
        unit_price = product.unit_list_price + bounded_float(-4.0, 6.0, 0.25, "price-adj", sales_key)
        unit_price = round(max(unit_price, product.unit_cost + 2.0), 2)
        gross_sales = round(quantity * unit_price, 2)
        discount_amount = round(gross_sales * discount_rate, 2)
        sales_amount = round(gross_sales - discount_amount, 2)
        margin_amount = round(sales_amount - (quantity * product.unit_cost), 2)

        sales_rows.append(
            {
                "SalesKey": sales_key,
                "OrderDate": fmt_date(order_date),
                "ShipDate": fmt_date(ship_date),
                "CustomerKey": customer.customer_key,
                "ProductKey": product.product_key,
                "StoreKey": store.store_key,
                "ChannelKey": channel_key,
                "PromotionKey": promotion_key,
                "OrderNumber": f"SO-{20230000 + sales_key}",
                "Quantity": quantity,
                "UnitPrice": f"{unit_price:.2f}",
                "UnitCost": f"{product.unit_cost:.2f}",
                "DiscountAmount": f"{discount_amount:.2f}",
                "SalesAmount": f"{sales_amount:.2f}",
                "MarginAmount": f"{margin_amount:.2f}",
                "ReturnedFlag": stable_int("returned", sales_key) % 17 == 0,
            }
        )

    target_rows: list[dict[str, object]] = []
    channel_multipliers = {1: 1.0, 2: 0.82, 3: 0.58}
    for month in months:
        seasonal = 1.0 + ((month.month - 6) / 40.0)
        for channel in channels:
            base_sales = 185000 * channel_multipliers[channel["ChannelKey"]] * seasonal
            wobble = bounded_float(-12000.0, 12000.0, 250.0, "target", month, channel["ChannelKey"])
            sales_target = round(base_sales + wobble, 2)
            margin_target = round(sales_target * (0.34 + 0.02 * channel["ChannelKey"]), 2)
            target_rows.append(
                {
                    "YearMonth": month.strftime("%Y-%m"),
                    "ChannelKey": channel["ChannelKey"],
                    "SalesTarget": f"{sales_target:.2f}",
                    "MarginTarget": f"{margin_target:.2f}",
                }
            )

    notes = {
        "fixture": "report-01-kitchen-sink",
        "date_range": f"{start.isoformat()} to {end.isoformat()}",
        "import_tables": [
            "Date",
            "Product",
            "Customer",
            "Store",
            "Channel",
            "Promotion",
            "Sales",
            "Targets",
        ],
        "manual_modeling_steps": [
            "Create the relationships from the fixture spec.",
            "Create measures, hierarchies, bookmarks, page setup, images, and visuals in Power BI Desktop.",
            "MonthName should be sorted by MonthNumber.",
        ],
    }

    manifest = {
        "dataset": "report-01-kitchen-sink",
        "Date_rows": write_csv(output_dir / "Date.csv", date_rows),
        "Product_rows": write_csv(output_dir / "Product.csv", product_rows),
        "Customer_rows": write_csv(output_dir / "Customer.csv", customer_rows),
        "Store_rows": write_csv(output_dir / "Store.csv", store_rows),
        "Channel_rows": write_csv(output_dir / "Channel.csv", channels),
        "Promotion_rows": write_csv(output_dir / "Promotion.csv", promotion_rows),
        "Sales_rows": write_csv(output_dir / "Sales.csv", sales_rows),
        "Targets_rows": write_csv(output_dir / "Targets.csv", target_rows),
    }
    (output_dir / "README.json").write_text(json.dumps(notes, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def kitchen_sink_products() -> list[ProductRow]:
    categories = {
        "Beverages": ["Tea", "Coffee", "Sparkling Water"],
        "Snacks": ["Chips", "Bars", "Nuts"],
        "Household": ["Cleaners", "Laundry", "Storage"],
        "Personal Care": ["Soap", "Oral Care", "Skincare"],
    }
    brands = ["Northwind", "Blue Pine", "Summit", "Harbor", "Aster", "Pioneer"]
    colors = ["Red", "Blue", "Green", "Black", "Silver", "White", "Amber", "Teal"]

    products: list[ProductRow] = []
    product_key = 1
    for category, subcategories in categories.items():
        for subcategory in subcategories:
            for variant in range(1, 5):
                brand = brands[(product_key - 1) % len(brands)]
                price = round(8 + (product_key % 9) * 2.65 + variant * 1.1, 2)
                cost = round(price * (0.46 + ((product_key + variant) % 4) * 0.04), 2)
                products.append(
                    ProductRow(
                        product_key=product_key,
                        sku=f"SKU-{product_key:04d}",
                        product_name=f"{brand} {subcategory} {variant}",
                        brand=brand,
                        category=category,
                        subcategory=subcategory,
                        color=colors[(product_key + variant) % len(colors)],
                        unit_list_price=price,
                        launch_date=date(2021 + (product_key % 3), ((product_key - 1) % 12) + 1, 1),
                        is_active=(product_key % 11) != 0,
                        unit_cost=cost,
                    )
                )
                product_key += 1
    return products


def kitchen_sink_customers() -> list[CustomerRow]:
    geo = [
        ("North", "USA", ["Seattle", "Portland", "Boise"]),
        ("South", "USA", ["Austin", "Dallas", "Atlanta"]),
        ("West", "USA", ["San Diego", "Phoenix", "Denver"]),
        ("Central", "USA", ["Chicago", "Columbus", "St. Louis"]),
        ("EMEA", "UK", ["London", "Manchester", "Bristol"]),
        ("APAC", "Australia", ["Sydney", "Melbourne", "Brisbane"]),
    ]
    segments = ["Consumer", "Small Business", "Enterprise"]
    rows: list[CustomerRow] = []
    for customer_key in range(1, 181):
        region, country, cities = geo[(customer_key - 1) % len(geo)]
        city = cities[(customer_key * 3) % len(cities)]
        rows.append(
            CustomerRow(
                customer_key=customer_key,
                customer_name=f"{choose(['Alex', 'Jordan', 'Taylor', 'Morgan', 'Casey', 'Riley'], 'fn', customer_key)} "
                f"{choose(['Parker', 'Nguyen', 'Chen', 'Patel', 'Garcia', 'Brown', 'Davis'], 'ln', customer_key)}",
                segment=segments[(customer_key + 1) % len(segments)],
                region=region,
                country=country,
                city=city,
                postal_code=f"{10000 + customer_key:05d}",
                signup_date=date(2021 + (customer_key % 3), ((customer_key * 5) % 12) + 1, ((customer_key * 7) % 27) + 1),
            )
        )
    return rows


def kitchen_sink_stores() -> list[StoreRow]:
    specs = [
        ("North", "Flagship"),
        ("North", "Outlet"),
        ("South", "Mall"),
        ("South", "Urban"),
        ("West", "Flagship"),
        ("West", "Outlet"),
        ("Central", "Urban"),
        ("Central", "Mall"),
        ("EMEA", "Flagship"),
        ("EMEA", "Urban"),
        ("APAC", "Flagship"),
        ("APAC", "Outlet"),
    ]
    rows: list[StoreRow] = []
    for store_key, (region, store_type) in enumerate(specs, start=1):
        rows.append(
            StoreRow(
                store_key=store_key,
                store_name=f"{region} {store_type} {store_key}",
                store_type=store_type,
                region=region,
                manager=f"{choose(['Mina', 'Owen', 'Priya', 'Lucas', 'Nora'], 'mgr-fn', store_key)} "
                f"{choose(['Lopez', 'Singh', 'Carter', 'Young', 'King'], 'mgr-ln', store_key)}",
                open_date=date(2018 + (store_key % 5), ((store_key * 2) % 12) + 1, 1),
            )
        )
    return rows


def kitchen_sink_promotions() -> list[PromotionRow]:
    types = ["Discount", "BOGO", "Bundle", "Loyalty"]
    rows: list[PromotionRow] = []
    for promotion_key in range(1, 9):
        start_month = ((promotion_key - 1) * 3) % 12 + 1
        start_date = date(2024, start_month, 1)
        rows.append(
            PromotionRow(
                promotion_key=promotion_key,
                promotion_name=f"{choose(['Spring', 'Summer', 'BackToSchool', 'Holiday'], 'promo', promotion_key)} Campaign {promotion_key}",
                promotion_type=types[(promotion_key - 1) % len(types)],
                start_date=start_date,
                end_date=start_date + timedelta(days=44 + promotion_key),
            )
        )
    return rows


def generate_model_heavy(output_dir: Path) -> dict[str, int | str]:
    date_start = date(2023, 1, 1)
    date_end = date(2025, 12, 31)
    all_dates = daterange(date_start, date_end)
    months = month_starts(date(2024, 1, 1), date(2025, 12, 1))

    departments = model_departments()
    cost_centers = model_cost_centers(departments)
    accounts = model_accounts()
    scenarios = [
        {"ScenarioKey": 1, "ScenarioName": "Actual", "ScenarioType": "Actual"},
        {"ScenarioKey": 2, "ScenarioName": "Budget", "ScenarioType": "Budget"},
        {"ScenarioKey": 3, "ScenarioName": "Forecast", "ScenarioType": "Forecast"},
    ]

    date_rows = [
        {
            "Date": fmt_date(day),
            "Year": day.year,
            "Quarter": f"Q{((day.month - 1) // 3) + 1}",
            "MonthNumber": day.month,
            "MonthName": day.strftime("%B"),
            "YearMonth": day.strftime("%Y-%m"),
            "FiscalYear": f"FY{day.year if day.month >= 7 else day.year - 1}",
            "FiscalQuarter": f"FQ{(((day.month - 7) % 12) // 3) + 1}",
            "FiscalMonthNumber": ((day.month - 7) % 12) + 1,
        }
        for day in all_dates
    ]

    gl_actuals: list[dict[str, object]] = []
    actual_key = 1
    for month in months:
        month_factor = 1.0 + (month.month / 25.0)
        for center in cost_centers:
            for account in accounts:
                department = departments[center["DepartmentKey"] - 1]
                base = 9500 + account["SortOrder"] * 135 + center["CostCenterKey"] * 18
                account_group_factor = {
                    "Revenue": 2.8,
                    "Payroll": 1.6,
                    "Operating Expense": 1.2,
                    "Services": 0.9,
                }[account["AccountGroup"]]
                division_factor = {
                    "Corporate": 1.35,
                    "Sales": 1.20,
                    "Operations": 1.12,
                    "Technology": 1.18,
                    "People": 0.88,
                }[department["Division"]]
                amount = round(
                    base * month_factor * account_group_factor * division_factor
                    + bounded_float(-850.0, 850.0, 25.0, "actual", month, center["CostCenterKey"], account["AccountKey"]),
                    2,
                )
                fte = round(
                    max(
                        0.25,
                        0.55
                        + (department["DepartmentKey"] % 4) * 0.4
                        + bounded_float(0.0, 2.4, 0.05, "fte", month, center["CostCenterKey"], account["AccountKey"]),
                    ),
                    2,
                )
                gl_actuals.append(
                    {
                        "ActualKey": actual_key,
                        "Date": fmt_date(month),
                        "DepartmentKey": department["DepartmentKey"],
                        "CostCenterKey": center["CostCenterKey"],
                        "AccountKey": account["AccountKey"],
                        "ScenarioKey": 1,
                        "Amount": f"{amount:.2f}",
                        "FTE": f"{fte:.2f}",
                        "CommentCode": choose(["BASE", "TREND", "SEASONAL", "PROJECT"], "comment", actual_key),
                    }
                )
                actual_key += 1

    budget_rows: list[dict[str, object]] = []
    forecast_rows: list[dict[str, object]] = []
    budget_key = 1
    forecast_key = 1
    for month in months:
        for department in departments:
            for account in accounts:
                anchor = 11000 + department["DepartmentKey"] * 180 + account["SortOrder"] * 120
                group_factor = {
                    "Revenue": 2.6,
                    "Payroll": 1.55,
                    "Operating Expense": 1.18,
                    "Services": 0.96,
                }[account["AccountGroup"]]
                budget_amount = round(
                    anchor * group_factor
                    + bounded_float(-650.0, 650.0, 25.0, "budget", month, department["DepartmentKey"], account["AccountKey"]),
                    2,
                )
                budget_fte = round(
                    0.8
                    + (department["DepartmentKey"] % 5) * 0.45
                    + bounded_float(0.0, 1.8, 0.05, "budget-fte", month, department["DepartmentKey"], account["AccountKey"]),
                    2,
                )
                forecast_amount = round(
                    budget_amount
                    * (0.97 + (stable_int("forecast-skew", month, department["DepartmentKey"], account["AccountKey"]) % 7) / 100.0),
                    2,
                )

                budget_rows.append(
                    {
                        "BudgetKey": budget_key,
                        "Date": fmt_date(month),
                        "DepartmentKey": department["DepartmentKey"],
                        "AccountKey": account["AccountKey"],
                        "ScenarioKey": 2,
                        "BudgetAmount": f"{budget_amount:.2f}",
                        "BudgetFTE": f"{budget_fte:.2f}",
                    }
                )
                forecast_rows.append(
                    {
                        "ForecastKey": forecast_key,
                        "Date": fmt_date(month),
                        "DepartmentKey": department["DepartmentKey"],
                        "AccountKey": account["AccountKey"],
                        "ScenarioKey": 3,
                        "ForecastAmount": f"{forecast_amount:.2f}",
                    }
                )
                budget_key += 1
                forecast_key += 1

    exchange_rates: list[dict[str, object]] = []
    for month in months:
        for currency_code, base_rate in [("USD", 1.0), ("EUR", 0.92), ("GBP", 0.79)]:
            if currency_code == "USD":
                rate = 1.0
            else:
                rate = round(
                    base_rate + bounded_float(-0.04, 0.04, 0.005, "fx", month, currency_code),
                    4,
                )
            exchange_rates.append(
                {
                    "Date": fmt_date(month),
                    "CurrencyCode": currency_code,
                    "RateToUSD": f"{rate:.4f}",
                }
            )

    notes = {
        "fixture": "report-02-model-heavy",
        "date_range": f"{date_start.isoformat()} to {date_end.isoformat()}",
        "import_tables": [
            "Date",
            "Department",
            "CostCenter",
            "Account",
            "Scenario",
            "GL_Actuals",
            "Budget",
            "Forecast",
            "ExchangeRate",
        ],
        "manual_modeling_steps": [
            "Create relationships, hidden columns, display folders, hierarchies, measures, and calculated artifacts from the fixture spec.",
            "MonthName should be sorted by MonthNumber.",
            "AccountName should be sorted by SortOrder.",
            "Add the calculated table Variance Bands manually.",
        ],
    }

    manifest = {
        "dataset": "report-02-model-heavy",
        "Date_rows": write_csv(output_dir / "Date.csv", date_rows),
        "Department_rows": write_csv(output_dir / "Department.csv", departments),
        "CostCenter_rows": write_csv(output_dir / "CostCenter.csv", cost_centers),
        "Account_rows": write_csv(output_dir / "Account.csv", accounts),
        "Scenario_rows": write_csv(output_dir / "Scenario.csv", scenarios),
        "GL_Actuals_rows": write_csv(output_dir / "GL_Actuals.csv", gl_actuals),
        "Budget_rows": write_csv(output_dir / "Budget.csv", budget_rows),
        "Forecast_rows": write_csv(output_dir / "Forecast.csv", forecast_rows),
        "ExchangeRate_rows": write_csv(output_dir / "ExchangeRate.csv", exchange_rates),
    }
    (output_dir / "README.json").write_text(json.dumps(notes, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def model_departments() -> list[dict[str, object]]:
    specs = [
        ("Corporate FP&A", "Corporate", True),
        ("Accounting", "Corporate", True),
        ("Field Sales", "Sales", False),
        ("Enterprise Sales", "Sales", False),
        ("Manufacturing", "Operations", False),
        ("Logistics", "Operations", False),
        ("Platform Engineering", "Technology", False),
        ("Business Systems", "Technology", False),
        ("People Operations", "People", True),
        ("Talent Acquisition", "People", True),
    ]
    rows: list[dict[str, object]] = []
    for department_key, (department_name, division, is_corporate) in enumerate(specs, start=1):
        rows.append(
            {
                "DepartmentKey": department_key,
                "DepartmentCode": f"D{department_key:03d}",
                "DepartmentName": department_name,
                "Division": division,
                "VPName": f"{choose(['Avery', 'Blake', 'Devon', 'Emerson', 'Finley'], 'vp-fn', department_key)} "
                f"{choose(['Howard', 'Reed', 'Foster', 'Bennett', 'Ward'], 'vp-ln', department_key)}",
                "IsCorporate": is_corporate,
            }
        )
    return rows


def model_cost_centers(departments: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    center_key = 1
    for department in departments:
        for suffix in ("Core", "Programs"):
            rows.append(
                {
                    "CostCenterKey": center_key,
                    "CostCenterCode": f"CC-{department['DepartmentCode']}-{suffix[:1]}",
                    "CostCenterName": f"{department['DepartmentName']} {suffix}",
                    "DepartmentKey": department["DepartmentKey"],
                    "ManagerName": f"{choose(['Jamie', 'Rowan', 'Skyler', 'Quinn'], 'cc-fn', center_key)} "
                    f"{choose(['Hayes', 'Bell', 'Myers', 'Price'], 'cc-ln', center_key)}",
                }
            )
            center_key += 1
    return rows


def model_accounts() -> list[dict[str, object]]:
    groups = {
        "Revenue": ["Product Revenue", "Service Revenue", "Partner Revenue"],
        "Payroll": ["Salaries", "Bonuses", "Benefits"],
        "Operating Expense": ["Travel", "Software", "Facilities"],
        "Services": ["Consulting", "Training", "Support"],
    }
    rows: list[dict[str, object]] = []
    account_key = 1
    sort_order = 10
    for group, names in groups.items():
        for subgroup_index, subgroup_name in enumerate(names, start=1):
            for leaf in range(1, 3 + 1):
                account_name = f"{subgroup_name} {leaf}"
                rows.append(
                    {
                        "AccountKey": account_key,
                        "AccountNumber": f"{4000 + account_key}",
                        "AccountName": account_name,
                        "AccountGroup": group,
                        "AccountSubgroup": subgroup_name,
                        "AccountType": "Expense" if group != "Revenue" else "Revenue",
                        "Sign": 1 if group != "Revenue" else -1,
                        "SortOrder": sort_order,
                    }
                )
                account_key += 1
                sort_order += 10
    return rows



# ---------------------------------------------------------------------------
# report-04-desktop-shapes
# ---------------------------------------------------------------------------

# CSV file name -> table name the build checklist renames it to in Desktop.
# File names stay filesystem-safe; the table names carry the special
# characters that the fixture exists to capture (issue #52).
DESKTOP_SHAPES_TABLES: list[tuple[str, str]] = [
    ("Date.csv", "Date"),
    ("Project.csv", "Project"),
    ("Person.csv", "Person"),
    ("RatesEUR.csv", "Rates (EUR)"),
    ("Task.csv", "Task"),
    ("Tag.csv", "Tag"),
    ("TaskTag.csv", "TaskTag"),
    ("TimeAndExpenses.csv", "Time & Expenses"),
    ("QANotes.csv", "Q/A Notes"),
    ("PortfolioTarget.csv", "Portfolio Target"),
]

DESKTOP_SHAPES_STATUSES: list[tuple[str, int]] = [
    ("Not started", 1),
    ("In progress", 2),
    ("Blocked", 3),
    ("Completed", 4),
]

DESKTOP_SHAPES_PRIORITIES: list[tuple[str, int]] = [
    ("Low", 1),
    ("Medium", 2),
    ("High", 3),
    ("Critical", 4),
]

DESKTOP_SHAPES_THEME_FILE = "Desktop Shapes Theme.json"
DESKTOP_SHAPES_IMAGE_FILE = "Team Logo.png"


def generate_desktop_shapes(output_dir: Path) -> dict[str, int | str]:
    """Project-delivery dataset for the Desktop-built shapes fixture.

    Small on purpose: the fixture exists to capture the JSON/TMDL shapes
    Power BI Desktop writes, not to exercise volume.
    """
    start = date(2024, 1, 1)
    end = date(2025, 12, 31)

    date_rows = [
        {
            "Date": fmt_date(day),
            "Year": day.year,
            "Quarter": f"Q{((day.month - 1) // 3) + 1}",
            "MonthNumber": day.month,
            "MonthName": day.strftime("%B"),
            "YearMonth": day.strftime("%Y-%m"),
            "IsWeekend": day.weekday() >= 5,
        }
        for day in daterange(start, end)
    ]

    portfolios = ["Customer Experience", "Platform", "Operations", "Compliance"]
    project_names = [
        "Checkout Redesign",
        "Self-Service Portal",
        "Mobile Notifications",
        "Data Platform Upgrade",
        "API Gateway",
        "Identity Service",
        "Warehouse Scheduling",
        "Fleet Tracking",
        "Support Tooling",
        "Audit Trail",
        "Retention Policy",
        "Access Review",
    ]
    project_priorities = ["High", "Medium", "Critical", "High", "Medium", "Low",
                          "Medium", "Low", "High", "Critical", "Low", "Medium"]
    priority_rank = dict(DESKTOP_SHAPES_PRIORITIES)
    projects: list[dict[str, object]] = []
    for index, name in enumerate(project_names):
        key = index + 1
        priority = project_priorities[index]
        projects.append(
            {
                "ProjectKey": key,
                "ProjectCode": f"P-{100 + key}",
                "ProjectName": name,
                "Portfolio": portfolios[index // 3],
                "Priority": priority,
                "PriorityRank": priority_rank[priority],
                "StartDate": fmt_date(date(2023, 9, 1) + timedelta(days=bounded_int(0, 270, "project-start", key))),
                "Budget": f"{bounded_float(25000.0, 250000.0, 500.0, 'project-budget', key):.2f}",
                "IsActive": key <= 10,
            }
        )

    rates = [
        {"Role": "Analyst", "HourlyRate": "68.00", "OvertimeMultiplier": "1.25"},
        {"Role": "Designer", "HourlyRate": "72.50", "OvertimeMultiplier": "1.25"},
        {"Role": "Developer", "HourlyRate": "85.00", "OvertimeMultiplier": "1.50"},
        {"Role": "Lead", "HourlyRate": "98.00", "OvertimeMultiplier": "1.50"},
        {"Role": "Manager", "HourlyRate": "105.00", "OvertimeMultiplier": "1.00"},
        {"Role": "Tester", "HourlyRate": "61.50", "OvertimeMultiplier": "1.25"},
    ]
    rate_by_role = {row["Role"]: float(row["HourlyRate"]) for row in rates}

    first_names = ["Adam", "Beata", "Carlos", "Dana", "Erik", "Fatima", "Gustav", "Hana",
                   "Ivan", "Julia", "Karel", "Lena", "Marek", "Nina", "Oskar", "Petra"]
    last_names = ["Novak", "Schmidt", "de Vries", "Kowalska", "Horak", "Weber", "Jansen",
                  "Nowak", "Dvorak", "Fischer", "Bakker", "Wojcik", "Svoboda", "Meyer",
                  "Visser", "Zielinska"]
    teams = ["Design", "Engineering", "QA", "Operations"]
    team_role = {"Design": "Designer", "Engineering": "Developer", "QA": "Tester", "Operations": "Analyst"}
    countries = ["Czechia", "Germany", "Netherlands", "Poland"]
    people: list[dict[str, object]] = []
    for index in range(16):
        key = index + 1
        team = teams[index % len(teams)]
        if key == 16:
            role = "Manager"
        elif index < len(teams):
            role = "Lead"
        else:
            role = team_role[team]
        people.append(
            {
                "PersonKey": key,
                "PersonName": f"{first_names[index]} {last_names[index]}",
                "Team": team,
                "Role": role,
                "Country": countries[(index * 3) % len(countries)],
                "StartDate": fmt_date(date(2019, 1, 1) + timedelta(days=bounded_int(0, 1800, "person-start", key))),
            }
        )
    role_by_person = {row["PersonKey"]: row["Role"] for row in people}

    status_rank = dict(DESKTOP_SHAPES_STATUSES)
    categories = ["Design", "Build", "Test", "Docs"]
    verbs = ["Draft", "Review", "Implement", "Test", "Document", "Refine", "Migrate", "Validate"]
    objects = ["login flow", "invoice export", "search index", "audit log", "onboarding email",
               "data model", "release notes", "API client", "dashboard", "access policy"]
    story_points = [1, 2, 3, 5, 8, 13]
    last_created = date(2025, 10, 31)
    created_span = (last_created - start).days

    tasks: list[dict[str, object]] = []
    for key in range(1, 601):
        roll = stable_int("task-status", key) % 100
        if roll < 45:
            status = "Completed"
        elif roll < 70:
            status = "In progress"
        elif roll < 88:
            status = "Not started"
        else:
            status = "Blocked"
        created = start + timedelta(days=stable_int("task-created", key) % (created_span + 1))
        due = min(created + timedelta(days=bounded_int(3, 60, "task-due", key)), end)
        completed: str = ""
        if status == "Completed":
            completed_day = created + timedelta(days=bounded_int(1, (due - created).days + 10, "task-done", key))
            completed = fmt_date(min(completed_day, end))
        estimate = bounded_float(2.0, 40.0, 0.5, "task-estimate", key)
        if status in ("Completed", "In progress", "Blocked"):
            factor = bounded_float(0.6, 1.6, 0.05, "task-actual", key)
            if status != "Completed":
                factor = round(factor / 2, 2)
            actual = round(estimate * factor * 2) / 2
        else:
            actual = 0.0
        tasks.append(
            {
                "TaskKey": key,
                "TaskCode": f"T-{key:04d}",
                "TaskName": f"{choose(verbs, 'task-verb', key)} {choose(objects, 'task-object', key)}",
                "ProjectKey": 1 + stable_int("task-project", key) % len(projects),
                "PersonKey": 1 + stable_int("task-person", key) % len(people),
                "Category": choose(categories, "task-category", key),
                "Status": status,
                "StatusRank": status_rank[status],
                "CreatedDate": fmt_date(created),
                "DueDate": fmt_date(due),
                "CompletedDate": completed,
                "EstimateHours": f"{estimate:.1f}",
                "ActualHours": f"{actual:.1f}",
                "StoryPoints": story_points[stable_int("task-points", key) % len(story_points)],
            }
        )

    tag_specs = [
        ("Frontend", "Technical"),
        ("Backend", "Technical"),
        ("Data", "Technical"),
        ("Security", "Quality"),
        ("Accessibility", "Quality"),
        ("Performance", "Quality"),
        ("Customer request", "Business"),
        ("Regulatory", "Business"),
    ]
    tags = [
        {"TagKey": index + 1, "TagName": name, "TagGroup": group}
        for index, (name, group) in enumerate(tag_specs)
    ]
    task_tags: list[dict[str, object]] = []
    for task in tasks:
        task_key = task["TaskKey"]
        count = stable_int("task-tag-count", task_key) % 4
        ranked = sorted(tags, key=lambda tag: stable_int("task-tag", task_key, tag["TagKey"]))
        for tag in sorted(ranked[:count], key=lambda tag: tag["TagKey"]):
            task_tags.append({"TaskKey": task_key, "TagKey": tag["TagKey"]})

    entries: list[dict[str, object]] = []
    all_days = daterange(start, end)
    for key in range(1, 1501):
        person_key = 1 + stable_int("te-person", key) % len(people)
        is_expense = stable_int("te-type", key) % 100 < 15
        if is_expense:
            hours = 0.0
            amount = bounded_float(15.0, 900.0, 0.05, "te-expense", key)
        else:
            hours = bounded_float(0.5, 8.0, 0.25, "te-hours", key)
            amount = round(hours * rate_by_role[role_by_person[person_key]], 2)
        entries.append(
            {
                "EntryKey": key,
                "EntryDate": fmt_date(all_days[stable_int("te-date", key) % len(all_days)]),
                "ProjectKey": 1 + stable_int("te-project", key) % len(projects),
                "PersonKey": person_key,
                "EntryType": "Expense" if is_expense else "Time",
                "Hours": f"{hours:.2f}",
                "Amount": f"{amount:.2f}",
                "IsBillable": stable_int("te-billable", key) % 10 < 7,
            }
        )

    qa_notes_text = [
        "Happy path verified",
        "Needs load test before release",
        "Accessibility review pending",
        "Regression suite green",
        "Open question on data retention",
        "Security sign-off received",
    ]
    qa_notes = [
        {
            "ProjectKey": project["ProjectKey"],
            "Reviewer": people[stable_int("qa-reviewer", project["ProjectKey"]) % len(people)]["PersonName"],
            "ReviewDate": fmt_date(date(2025, 1, 1) + timedelta(days=bounded_int(0, 330, "qa-date", project["ProjectKey"]))),
            "QAScore": bounded_int(1, 5, "qa-score", project["ProjectKey"]),
            "Note": choose(qa_notes_text, "qa-note", project["ProjectKey"]),
        }
        for project in projects
    ]

    portfolio_targets = [
        {
            "Portfolio": portfolio,
            "Year": year,
            "TargetHours": bounded_int(16, 48, "pt-hours", portfolio, year) * 50,
            "TargetBudget": f"{bounded_float(150000.0, 600000.0, 1000.0, 'pt-budget', portfolio, year):.2f}",
        }
        for portfolio in portfolios
        for year in (2024, 2025)
    ]

    tables: dict[str, list[dict[str, object]]] = {
        "Date.csv": date_rows,
        "Project.csv": projects,
        "Person.csv": people,
        "RatesEUR.csv": rates,
        "Task.csv": tasks,
        "Tag.csv": tags,
        "TaskTag.csv": task_tags,
        "TimeAndExpenses.csv": entries,
        "QANotes.csv": qa_notes,
        "PortfolioTarget.csv": portfolio_targets,
    }
    assert [name for name, _ in DESKTOP_SHAPES_TABLES] == list(tables)

    manifest: dict[str, int | str] = {"dataset": "report-04-desktop-shapes"}
    for file_name, rows in tables.items():
        manifest[f"{Path(file_name).stem}_rows"] = write_csv(output_dir / file_name, rows)

    (output_dir / DESKTOP_SHAPES_THEME_FILE).write_text(
        json.dumps(desktop_shapes_theme(), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (output_dir / DESKTOP_SHAPES_IMAGE_FILE).write_bytes(desktop_shapes_logo_png())

    notes = {
        "fixture": "report-04-desktop-shapes",
        "date_range": f"{start.isoformat()} to {end.isoformat()}",
        "import_order": [file_name for file_name, _ in DESKTOP_SHAPES_TABLES],
        "csv_to_table": {file_name: table for file_name, table in DESKTOP_SHAPES_TABLES},
        "other_inputs": {
            DESKTOP_SHAPES_THEME_FILE: "Custom theme imported in Desktop (file name contains a space, issue #29).",
            DESKTOP_SHAPES_IMAGE_FILE: "Image inserted in Desktop (file name contains a space, issue #29).",
        },
        "manual_modeling_steps": [
            "Follow BUILD-CHECKLIST.md step by step; everything is built by hand in Power BI Desktop.",
            "Rename each imported table to the name in csv_to_table.",
            "Task[CompletedDate] is blank for tasks that are not Completed.",
            "Project[Priority] sorts by Project[PriorityRank]; Task[Status] sorts by Task[StatusRank].",
            "Portfolio Target relates to Project on the non-unique Portfolio column (many-to-many).",
            "Q/A Notes has exactly one row per project (one-to-one with Project).",
        ],
    }
    (output_dir / "README.json").write_text(json.dumps(notes, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def desktop_shapes_theme() -> dict[str, object]:
    """Minimal custom theme. textClasses are left out on purpose: the build
    checklist sets them through Desktop's Customize theme dialog (issue #49)."""
    return {
        "name": "Desktop Shapes Theme",
        "dataColors": [
            "#118DFF",
            "#1F3A5F",
            "#20A741",
            "#F2A900",
            "#D64550",
            "#8E6CEF",
            "#A0A0A0",
            "#00B7C3",
        ],
        "foreground": "#252423",
        "background": "#FFFFFF",
        "tableAccent": "#118DFF",
        "good": "#20A741",
        "neutral": "#F2A900",
        "bad": "#D64550",
        "maximum": "#1F3A5F",
        "center": "#F2A900",
        "minimum": "#DEEFFF",
    }


def desktop_shapes_logo_png(width: int = 96, height: int = 32) -> bytes:
    """Byte-stable PNG: three colour bands, deflate in stored (uncompressed)
    blocks so the output doesn't depend on the zlib build."""
    bands = [(0x1F, 0x3A, 0x5F), (0x11, 0x8D, 0xFF), (0x20, 0xA7, 0x41)]
    raw = bytearray()
    for _y in range(height):
        raw.append(0)  # filter type: none
        for x in range(width):
            raw.extend(bands[min(x * len(bands) // width, len(bands) - 1)])
    data = bytes(raw)

    stream = bytearray(b"\x78\x01")
    for offset in range(0, len(data), 65535):
        chunk = data[offset:offset + 65535]
        final = 1 if offset + 65535 >= len(data) else 0
        stream.append(final)
        stream.extend(struct.pack("<HH", len(chunk), len(chunk) ^ 0xFFFF))
        stream.extend(chunk)
    stream.extend(struct.pack(">I", zlib.adler32(data)))

    def png_chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload))
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", bytes(stream))
        + png_chunk(b"IEND", b"")
    )


if __name__ == "__main__":
    main()
