"""Bulk invoice PDF generation from CSV/JSON input."""
import argparse
import csv
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
TEMPLATE_NAME = "invoice_template.html"


def load_rows(input_path):
    path = Path(input_path)
    if path.suffix.lower() == ".json":
        with open(path) as f:
            return json.load(f)
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["line_items"] = json.loads(row["line_items"]) if row.get("line_items") else []
            rows.append(row)
    return rows


def compute_subtotal(line_items):
    subtotal = Decimal("0.00")
    for item in line_items:
        qty = Decimal(str(item.get("quantity", 1)))
        price = Decimal(str(item.get("unit_price", 0)))
        line_total = (qty * price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        item["line_total"] = str(line_total)
        subtotal += line_total
    return subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def render_invoice(env, row):
    line_items = row.get("line_items", [])
    subtotal = compute_subtotal(line_items)
    tax_rate = Decimal(str(row.get("tax_rate", 0) or 0))
    tax = (subtotal * tax_rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total = subtotal + tax

    template = env.get_template(TEMPLATE_NAME)
    return template.render(
        invoice_number=row.get("invoice_number", ""),
        client_name=row.get("client_name", ""),
        due_date=row.get("due_date", ""),
        line_items=line_items,
        subtotal=subtotal,
        tax=tax,
        tax_rate=tax_rate,
        total=total,
    )


def generate(input_path, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    rows = load_rows(input_path)

    for row in rows:
        html_content = render_invoice(env, row)
        invoice_number = row.get("invoice_number", "untitled")
        output_path = output_dir / f"invoice_{invoice_number}.pdf"
        HTML(string=html_content).write_pdf(str(output_path))
        print(f"wrote {output_path}")

    print(f"generated {len(rows)} invoice(s) in {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Generate invoice PDFs in bulk from CSV/JSON input.")
    parser.add_argument("--input", required=True, help="Path to CSV or JSON input file")
    parser.add_argument("--output", required=True, help="Directory to write generated PDFs")
    args = parser.parse_args()
    generate(args.input, args.output)


if __name__ == "__main__":
    main()
