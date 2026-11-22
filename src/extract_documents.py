"""Structured data extraction from incoming documents via AWS Textract."""
import argparse
import json
import os
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv()

CONFIDENCE_THRESHOLD = float(os.getenv("EXTRACTION_CONFIDENCE_THRESHOLD", "85"))

FIELD_ALIASES = {
    "invoice #": "invoice_number",
    "invoice no.": "invoice_number",
    "inv number": "invoice_number",
    "invoice number": "invoice_number",
    "bill to": "client_name",
    "due date": "due_date",
    "total due": "total",
    "amount due": "total",
}


def normalize_field_name(raw_key):
    key = raw_key.strip().lower().rstrip(":")
    return FIELD_ALIASES.get(key, key.replace(" ", "_"))


def get_block_text(block, blocks_by_id):
    text = []
    for relationship in block.get("Relationships", []):
        if relationship["Type"] != "CHILD":
            continue
        for child_id in relationship["Ids"]:
            child = blocks_by_id[child_id]
            if child["BlockType"] == "WORD":
                text.append(child["Text"])
            elif child["BlockType"] == "SELECTION_ELEMENT" and child.get("SelectionStatus") == "SELECTED":
                text.append("X")
    return " ".join(text)


def extract_key_values(blocks, blocks_by_id):
    fields = {}
    key_blocks = [b for b in blocks if b["BlockType"] == "KEY_VALUE_SET" and "KEY" in b.get("EntityTypes", [])]

    for key_block in key_blocks:
        key_text = get_block_text(key_block, blocks_by_id)
        value_text, confidence = "", key_block.get("Confidence", 0)

        for relationship in key_block.get("Relationships", []):
            if relationship["Type"] != "VALUE":
                continue
            for value_id in relationship["Ids"]:
                value_block = blocks_by_id[value_id]
                value_text = get_block_text(value_block, blocks_by_id)
                confidence = min(confidence, value_block.get("Confidence", 0))

        field_name = normalize_field_name(key_text)
        fields[field_name] = {
            "value": value_text,
            "confidence": round(confidence, 1),
            "needs_review": confidence < CONFIDENCE_THRESHOLD,
        }
    return fields


def extract_tables(blocks, blocks_by_id):
    tables = []
    for block in blocks:
        if block["BlockType"] != "TABLE":
            continue
        cells = {}
        for relationship in block.get("Relationships", []):
            if relationship["Type"] != "CHILD":
                continue
            for cell_id in relationship["Ids"]:
                cell = blocks_by_id[cell_id]
                if cell["BlockType"] != "CELL":
                    continue
                row, col = cell["RowIndex"], cell["ColumnIndex"]
                cells.setdefault(row, {})[col] = get_block_text(cell, blocks_by_id)

        rows = [[cells[r].get(c, "") for c in sorted(cells[r])] for r in sorted(cells)]
        tables.append(rows)
    return tables


def extract_document(client, file_path):
    with open(file_path, "rb") as f:
        response = client.analyze_document(
            Document={"Bytes": f.read()},
            FeatureTypes=["FORMS", "TABLES"],
        )

    blocks = response["Blocks"]
    blocks_by_id = {b["Id"]: b for b in blocks}

    return {
        "source_file": str(file_path),
        "fields": extract_key_values(blocks, blocks_by_id),
        "tables": extract_tables(blocks, blocks_by_id),
    }


def main():
    parser = argparse.ArgumentParser(description="Extract structured data from documents via AWS Textract.")
    parser.add_argument("--input", required=True, help="File or directory of PDFs/images to process")
    parser.add_argument("--output", required=True, help="Path to write extracted JSON results")
    args = parser.parse_args()

    client = boto3.client("textract", region_name=os.getenv("AWS_REGION", "us-east-1"))
    input_path = Path(args.input)
    files = [input_path] if input_path.is_file() else sorted(input_path.glob("*.pdf"))

    results = [extract_document(client, f) for f in files]

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    print(f"extracted {len(results)} document(s) to {args.output}")


if __name__ == "__main__":
    main()
