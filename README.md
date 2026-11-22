# Bulk Document Pipeline Toolkit

> Avalux (https://avalux.io) is a full-stack AI automation agency. We build and ship automation systems for small and midsize businesses, and we open-source the toolkits we use as building blocks so teams can see how we actually write code before they hire us. This repo is one piece of that library. See the rest at [avalux-open-source](https://github.com/elikem2021/avalux-open-source).

## Why this exists

Most automation projects we see follow the same arc. A team wires up a CRM, connects a scheduling tool, automates a payment flow, maybe adds a Slack notification when a deal closes. Everything moves except one thing: documents. Someone is still opening a spreadsheet template by hand to build an invoice, copying numbers into a statement, or retyping data from a scanned form into whatever system needs it next.

Documents resist automation for a predictable reason. Generating them well means handling layout, pagination, and formatting, not just filling in a template string. Reading them well means handling the fact that incoming PDFs, scans, and photos are inconsistent, and a regex that worked on one vendor's invoice breaks on the next one's. Teams either give up and keep a person in the loop permanently, or they build something fragile: a script tied to one exact PDF layout, or worse, a scraper pointed at some portal that was never meant to be automated.

This toolkit is the piece that's usually missing. It's a generate-and-extract pipeline built around two real jobs: producing accurate, formatted documents in bulk (invoices, statements, client deliverables), and pulling structured data back out of documents that come in from the outside world (vendor invoices, signed forms, scanned paperwork). Both halves use real, documented APIs. No portal scraping, no brittle PDF byte manipulation, no screen reading hacks that break the moment a vendor changes their invoice layout by five pixels.

## Who this is for

- Agencies, bookkeepers, and back office teams that generate invoices, statements, or client facing reports at volume and are still doing it by hand or with a half working mail merge
- Finance and ops teams that receive vendor invoices, remittances, or intake forms and currently retype them into a spreadsheet or accounting system
- Teams that have already automated the rest of a workflow (CRM, scheduling, payments) and keep hitting a wall at "someone still has to deal with the documents"
- Developers who want a working example of document generation and document extraction built on real APIs, as a starting point for something more specific

This is not for anyone looking for a finished SaaS invoicing product, and it's not for anyone who needs to pull data out of a system with no API. If the data source is a portal with no API and no export, that is a different and much more fragile problem than this toolkit solves, and we don't build that way.

## What's in the box

```
bulk-document-pipeline-toolkit/
├── src/
│   ├── generate_invoices.py     # bulk PDF generation from CSV/JSON + HTML template
│   └── extract_documents.py     # structured data extraction from incoming PDFs/images
├── templates/
│   └── invoice_template.html    # Jinja2 + CSS invoice template, built for pagination
├── data/
│   └── invoices.sample.csv      # sample input data for generation
├── output/                      # generated PDFs and extracted JSON land here (gitignored)
├── .env.example
├── requirements.txt
├── LICENSE
└── README.md
```

Two scripts, one template, and a sample dataset. That's intentionally small. The point isn't to hand you a framework, it's to hand you a correct, working shape for both halves of the pipeline that you can extend into your actual stack.

## Quick start

```bash
git clone https://github.com/elikem2021/bulk-document-pipeline-toolkit
cd bulk-document-pipeline-toolkit

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env

# Generate a batch of invoice PDFs from the sample CSV
python src/generate_invoices.py --input data/invoices.sample.csv --output output/

# Extract structured data back out of a folder of PDFs (requires AWS credentials in .env)
python src/extract_documents.py --input output/ --output output/extracted.json
```

`generate_invoices.py` runs with no external API and no credentials. `extract_documents.py` calls AWS Textract, so it needs AWS credentials in `.env` and will incur Textract's per page cost.

## How generation works

`generate_invoices.py` reads rows from a CSV or JSON file (one row per invoice: client name, invoice number, due date, line items, totals), renders each row into the Jinja2 template at `templates/invoice_template.html`, and converts the resulting HTML to a PDF using WeasyPrint.

The reason this is built on HTML and CSS rather than drawing directly onto a PDF canvas (the usual approach with libraries like reportlab) is maintainability. A finance person or designer can open `invoice_template.html` and change the layout, fonts, or branding without touching Python. Print CSS handles page breaks, headers repeating across pages, and multi page line item tables correctly, which is the part that is genuinely hard to get right by hand positioning text on a PDF canvas. The script itself just handles the loop: read a row, render it, render the PDF, write the file, move to the next row.

Line items are summed in the script rather than trusted from the input file, because input data, especially anything that originated in a spreadsheet, is the single most common source of silent invoice errors. Totals should always be a computed, auditable value, not a free text field someone typed in.

## How extraction works

`extract_documents.py` sends each document to AWS Textract's `AnalyzeDocument` API with the `FORMS` and `TABLES` feature types enabled. Textract returns a block based structure: individual text blocks, key value pairs it identified as form fields, and table cells with row and column coordinates. The script walks that structure and flattens it into a clean JSON record per document: a dict of detected key value fields, plus a list of extracted tables as arrays of rows.

Two details matter here that a lot of "AI document extraction" demos skip over:

**Confidence scores.** Every field Textract returns comes with a confidence score from 0 to 100. The script tags each extracted field with its confidence and flags anything under a configurable threshold (default 85) for manual review instead of writing it straight into downstream data. Treating every extracted value as equally trustworthy is how extraction pipelines quietly corrupt a general ledger. Low confidence fields should route to a human, not straight into QuickBooks.

**Field name normalization.** Textract returns the key exactly as it appears on the document: "Invoice #", "Invoice No.", "INV Number" might all show up depending on who sent the document. The script includes a small mapping layer (`FIELD_ALIASES` in the script) that maps known variants to canonical field names, with a fallback that just slugifies anything not in the map. This is the part you will spend the most time customizing once you point this at real vendor documents, because every vendor formats things slightly differently, and the mapping table is where that variance gets absorbed instead of leaking into your data.

Textract is the API used here because it's well documented, has clear per page pricing, and handles both printed and handwritten forms reasonably well. The extraction logic (walk key value blocks, walk table blocks, normalize field names, flag low confidence) is the same shape you'd use against Azure Document Intelligence or Google Document AI. Swapping providers means swapping the client call at the top of the script, not rewriting the pipeline.

## This is scaffolding, not a finished system

Open source does not mean production ready. Before this runs real invoicing or real vendor document intake, you still need to add, at minimum:

- **Storage.** Right now output lands in a local folder. Real usage needs documents written to S3 or equivalent, with a retention and access policy that matches what's actually in those files. Invoices and vendor documents are sensitive.
- **Idempotency and retries.** Textract calls can fail or time out. The sample script does not retry or dedupe; a production version needs a queue (SQS, Celery, whatever fits your stack) and a way to avoid double processing the same document.
- **Template hardening.** The sample invoice template is deliberately simple. Multi currency support, tax rules by jurisdiction, and credit memos all need real handling, not just more template variables.
- **Validation at the boundary.** The extraction script flags low confidence fields but does not block anything from being written. You need a review step and a decision about what happens to flagged records before they touch a ledger.
- **Volume and rate limits.** Textract has throughput limits per account. At real volume you need batching and backoff, not a tight loop over a folder.

None of that is hard, but all of it is the difference between a working script and something you'd trust with actual money or actual client deliverables. That gap is exactly where we do our client work.

## Why we built this

We kept running into the same pattern across client engagements: a business has automated the parts of their workflow that look like "automation" (routing leads, syncing a CRM, sending reminders), and the part that actually eats the most staff time, producing and processing documents, is still entirely manual, because nobody wanted to be the one to build a PDF pipeline. We built this toolkit as the base layer we reach for on those engagements, then customize the template, the field mapping, and the storage destination for whatever the client's actual accounting or CRM system expects.

We're putting it up as open source for three reasons. First, so you can see the actual quality and shape of code we write before you hire us, not a sales deck. Second, because for a lot of teams this alone, run and extended in house, solves the problem. Third, because if you get this far and realize you need it integrated into QuickBooks, NetSuite, a client portal, or a document management system with proper auth, retries, and monitoring, that's the work we do. Reach out through [avalux.io](https://avalux.io).

## Avalux's other open source projects

- [freight-eta-toolkit](https://github.com/elikem2021/freight-eta-toolkit): geofencing and ETA calculation toolkit for logistics and dispatch teams
- [avalux-open-source](https://github.com/elikem2021/avalux-open-source): the index of everything we've open sourced, start here if you want the full list

## License

MIT. See [LICENSE](LICENSE). Use it, fork it, put it into production, sell things built on top of it. Attribution is appreciated but not required.

## Keywords

bulk pdf generation workflow, automated invoice generation, bulk document data extraction, batch invoice generation python, PDF generation pipeline, document data extraction API, AWS Textract invoice extraction, automated document processing, back office automation toolkit, templated PDF invoices, structured document extraction, open source invoicing automation
