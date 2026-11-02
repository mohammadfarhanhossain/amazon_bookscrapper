# Amazon Books Scraper — Unified Pipeline & Database

A production-grade, fault-tolerant scraping, cleaning, normalization, and relational catalog pipeline for Amazon Books, structured identically to `wafilife scrapper` and `rokomar_scrapper`.

---

## Price & Currency Format

> [!IMPORTANT]
> All prices in `clean_books.csv`, `all_scraped_book_rows.csv`, and `master.csv` are explicitly formatted with the dollar sign (`$`) (e.g. `$16.29`, `$24.99`, `$4.99`), with the currency column set to `USD`, ensuring they are never mistaken for Bangladeshi Taka (BDT).

---

## Daily Scraping & Automation

- Run the pipeline with `--scrape` from the virtual environment:

```powershell
& ".\.venv\Scripts\python.exe" "amazon_pipeline.py" --scrape
```

- Or execute the scheduled daily wrapper script:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_amazon_daily.ps1
```

---

## Features & Reliability Design

### 1. Bot-Detection & Anti-Fingerprinting (Playwright Stealth)
- Amazon employs aggressive Cloudflare and AWS WAF captchas on automated requests.
- The pipeline uses a headless Playwright Chromium instance coupled with `playwright-stealth` to emulate realistic browser signatures and pass Cloudflare / Amazon Robot Checks.

### 2. Atomic Writes
- All CSVs and progress files are written to `.tmp` files first and replaced using `atomic_replace`.
- Prevents file corruption during unexpected termination or network dropouts.

### 3. State & Resume Behavior
- State is saved in `data/state/scraping_progress_categories.txt`.
- If blocked or stopped, the pipeline resumes directly from the next category/page.

### 4. Dollar Price Formatting
- Automatically parses and ensures `$XX.XX` formatting on all catalog prices.

---

## How to Run

### 1. Default Scraping (Main Departments)
```powershell
& ".\.venv\Scripts\python.exe" "amazon_pipeline.py" --scrape
```

### 2. Deep Multi-Source Scraping (Bestsellers + Subcategories + Charts + Search)
```powershell
& ".\.venv\Scripts\python.exe" "amazon_pipeline.py" --scrape-all
```

### 3. Targeted Modes & Features
- **Auto-Discover Subcategories** (explores nested departments from Amazon's sidebar):
  ```powershell
  & ".\.venv\Scripts\python.exe" "amazon_pipeline.py" --scrape --discover-subcategories
  ```

- **Include Hot New Releases, Movers & Shakers & Most Wished For**:
  ```powershell
  & ".\.venv\Scripts\python.exe" "amazon_pipeline.py" --scrape --include-charts
  ```

- **Scrape by Search Keywords**:
  ```powershell
  & ".\.venv\Scripts\python.exe" "amazon_pipeline.py" --mode search --search-keywords "python, artificial intelligence, science fiction" --max-pages 3
  ```

### 4. Build Clean CSVs & Master Only
```powershell
& ".\.venv\Scripts\python.exe" "amazon_pipeline.py" --build-only
```

### 5. Verify Data Integrity & Dollar Prices
```powershell
& ".\.venv\Scripts\python.exe" "amazon_pipeline.py" --verify-only
```

### 6. Refresh Raw Category Seeds
```powershell
& ".\.venv\Scripts\python.exe" "amazon_pipeline.py" --force-list
```

---

## Directory & File Layout

```
amazon_scrapper/
├── data/
│   ├── archive/                     # Archived older dumps
│   ├── logs/                        # Daily run logs (stdout & stderr)
│   ├── processed/                   # Cleaned entity CSVs, clean_*.csv, master.csv
│   │   ├── all_scraped_book_rows.csv
│   │   ├── Amazon_Category_Books_Data.csv
│   │   ├── clean_authors.csv
│   │   ├── clean_books.csv
│   │   ├── clean_categories.csv
│   │   ├── clean_publishers.csv
│   │   └── master.csv
│   ├── raw/                         # Raw category seed list (Amazon_All_Categories.csv)
│   └── state/                       # Resume progress markers
├── database/
│   └── migrations/
│       ├── 001_catalog_schema.sql   # Relational MySQL catalog schema
│       └── 002_seed_sources.sql     # Source metadata seed
├── all_scraped_book_rows.csv        # Merged scraped book rows with '$' prices
├── clean_authors.csv                # Relational authors table
├── clean_books.csv                  # Relational books table with '$' prices
├── clean_categories.csv             # Relational categories table
├── clean_publishers.csv             # Relational publishers table
├── master.csv                       # Master denormalized catalog with '$' prices
├── docker-compose.yml               # Local MySQL & Chroma DB containers
├── requirements.txt                 # Python dependencies
├── run_amazon_daily.ps1             # Daily scheduled task runner
├── amazon_pipeline.py               # Core unified pipeline
└── README.md                        # Documentation
```
