# 🧾 Invoice Agent — X12 → ERP with AI/Redis/Apify

![Python](https://img.shields.io/badge/python-3.12-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.112-009688.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-1.38-FF4B4B.svg)
![Redis](https://img.shields.io/badge/Redis-Anomaly%20Detection-red.svg)
![Apify](https://img.shields.io/badge/Apify-Vendor%20Enrichment-yellow.svg)
![Hackathon](https://img.shields.io/badge/Hackathon-Ready-success.svg)

## 🚀 Overview
This project automates the ingestion and validation of **EDI X12 810 Invoices** into a mock ERP system.  
It parses invoices, validates schema rules, enriches vendor data, detects anomalies with Redis, and provides a **Streamlit dashboard** to review results.

### Problem
Manual invoice validation is **error-prone, slow, and costly**, especially when vendors send inconsistent data.

### Solution
I built an **agentic workflow** that:
- Parses raw **X12 EDI** invoices into structured JSON
- Runs **validation checks** (invoice number, totals, line items, etc.)
- Calculates **anomaly scores** using Redis time-series history
- Performs **vendor enrichment** via Apify
- Automatically **posts valid invoices** into a mock ERP
- Surfaces all invoices (Posted + Rejected) in a **Streamlit dashboard** with details, explanations, enrichment, and line items

---

## ⚙️ Features
- ✅ **EDI Parsing** → Extracts invoice metadata, parties, line items, totals  
- ✅ **Validation** → Detects missing fields, totals mismatches, line count errors  
- ✅ **Anomaly Detection** → Redis-based rolling z-scores for vendor spending  
- ✅ **Vendor Enrichment** → (Apify) Add website, category, GL suggestion  
- ✅ **ERP Simulation** → Mock FastAPI ERP service  
- ✅ **Streamlit Dashboard** → Interactive UI with metrics, rejected/posted invoices, error explanations, enrichment, and line items  
- ✅ **Batch Upload** → Process multiple invoices in one run (`batch_ingest.py`)  

---

## 📂 Project Structure
```
invoice-agent-x12-starter/
├── app/
│   ├── ingest.py              # Main entry: parse + validate + enrich + ERP post
│   ├── batch_ingest.py        # Batch ingestion of invoices
│   ├── dashboard.py           # Streamlit UI
│   ├── validate.py            # Validation logic
│   ├── erp_client.py          # Mock ERP client
│   ├── state.py               # SQLite state recorder
│   ├── integrations/          # External integrations
│   │   ├── redis_anomaly.py   # Redis anomaly scoring
│   │   ├── apify_enrich.py    # Vendor enrichment
│   │   └── (future: gladia_stt, honeyhive, etc.)
│   └── x12/                   # EDI parsing utilities
│       └── parse_810.py
├── data/
│   ├── inbound/               # Raw .edi invoice files
│   ├── processed/             # Valid invoices → JSON
│   └── rejects/               # Invalid invoices → JSON + explanations
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🛠️ Setup

### 1. Clone the repo
```bash
git clone https://github.com/<your-username>/invoice-agent-x12-starter.git
cd invoice-agent-x12-starter
```

### 2. Create and activate virtual env
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment
Copy the example env:
```bash
cp .env.example .env
```

Edit `.env` with your keys (Redis, Apify, etc.):

```ini
# Redis connection
REDIS_URL=redis://default:<password>@<endpoint>:<port>

# Apify (optional)
APIFY_TOKEN=your_apify_token
```

---

## ▶️ Usage

### Start Mock ERP
```bash
uvicorn mock_erp.api:app --reload
```

### Ingest a single invoice
```bash
python -m app.ingest data/inbound/ACME_GOOD.edi
```

### Ingest all invoices (batch)
```bash
python batch_ingest.py --pattern "data/inbound/*.edi"
```

### Launch Streamlit Dashboard
```bash
streamlit run app/dashboard.py
```

---

## 📊 Dashboard
- View **metrics** (processed, posted, rejected)  
- Browse **all invoices** with status, anomaly, and ERP ID  
- Select an invoice to see:  
  - ❌ Errors & explanations (for rejected)  
  - ✅ ERP posting details (for posted)  
  - 🔎 Vendor enrichment (website, category, GL suggestion)  
  - 📦 Line items table with GL accounts  

---

## ✅ Example Run

```bash
python batch_ingest.py --pattern "data/inbound/GOOD_*.edi"
```

Output:
```
[POSTED] INV1002 | ERP_ID=24646585... | anomaly=0.0
[POSTED] INV1003 | ERP_ID=797827f... | anomaly=-0.16
[REJECTED] INV1001: [('TDS', 'Totals mismatch: ...')]
```

---

## 📌 Future Scope
- 🎙 **Gladia** → Voice actions (“Approve” / “Reject”) via audio notes  
- 📡 **HoneyHive** → Experiment & track metrics/logging  
- 🔐 **Stytch** → Authentication for the dashboard  
- ☁️ **AWS S3** → Upload raw EDI files to cloud for auto-ingestion  
- 📈 **Redis VL** → Vector similarity search on vendor/invoice embeddings  

---

## 🏆 Hackathon Prizes Alignment
- **Redis VL Innovator** → anomaly + vector search  
- **Best use of Apify** → vendor enrichment  
- **Best use of AWS** → ERP + data hosting  
- **Future integrations (Gladia, HoneyHive, Stytch)** can unlock additional categories
- **Video link** https://drive.google.com/file/d/1VWXxDVVkfEmxuwlpyQFZvLHOmEKEP0pL/view?usp=drive_link

---

✨ Built with love by **Sinchana Gupta Garla Venkatesha** 💡
