import argparse
import json
import os
import random
import re
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from playwright.sync_api import sync_playwright
from playwright_stealth.stealth import Stealth
from sqlalchemy import create_engine, text

stdout_reconfigure = getattr(sys.stdout, "reconfigure", None)
if callable(stdout_reconfigure):
    stdout_reconfigure(encoding="utf-8")

PROJECT_DIR = Path(__file__).resolve().parent
RAW_DIR = PROJECT_DIR / "data" / "raw"
PROCESSED_DIR = PROJECT_DIR / "data" / "processed"
STATE_DIR = PROJECT_DIR / "data" / "state"
LOG_DIR = PROJECT_DIR / "data" / "logs"
ARCHIVE_DIR = PROJECT_DIR / "data" / "archive"

for directory in [RAW_DIR, PROCESSED_DIR, STATE_DIR, LOG_DIR, ARCHIVE_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

DB_USER = os.getenv("AMAZON_DB_USER", "root")
DB_PASS = os.getenv("AMAZON_DB_PASS", "farhan")
DB_HOST = os.getenv("AMAZON_DB_HOST", "localhost")
DB_PORT = os.getenv("AMAZON_DB_PORT", "3306")
DB_NAME = os.getenv("AMAZON_DB_NAME", "amazon_db")

DOMAIN = "https://www.amazon.com"
INVALID_TEXTS = {"", "nan", "none", "not listed", "unknown", "unknown author", "unknown publisher"}
BLOCK_INDICATORS = [
    "validatecaptcha",
    "robot check",
    "type the characters you see in this image",
    "sorry, we just need to make sure you're not a robot",
    "enter the characters you see below",
    "images-amazon.com/captcha",
]

# 1. Standard Amazon Books 20 Departments (Bestsellers)
DEFAULT_CATEGORIES = [
    {"name": "Literature & Fiction", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/17", "node": "17"},
    {"name": "Mystery, Thriller & Suspense", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/18", "node": "18"},
    {"name": "Science Fiction & Fantasy", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/25", "node": "25"},
    {"name": "Biographies & Memoirs", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/2", "node": "2"},
    {"name": "Business & Money", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/3", "node": "3"},
    {"name": "Computers & Technology", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/5", "node": "5"},
    {"name": "Self-Help", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/4736", "node": "4736"},
    {"name": "History", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/9", "node": "9"},
    {"name": "Science & Math", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/75", "node": "75"},
    {"name": "Romance", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/23", "node": "23"},
    {"name": "Children's Books", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/4", "node": "4"},
    {"name": "Teen & Young Adult", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/28", "node": "28"},
    {"name": "Comics & Graphic Novels", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/4366", "node": "4366"},
    {"name": "Cookbooks, Food & Wine", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/6", "node": "6"},
    {"name": "Religion & Spirituality", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/22", "node": "22"},
    {"name": "Health, Fitness & Dieting", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/10", "node": "10"},
    {"name": "Arts & Photography", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/1", "node": "1"},
    {"name": "Education & Teaching", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/8975347011", "node": "8975347011"},
    {"name": "Politics & Social Sciences", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/3377866011", "node": "3377866011"},
    {"name": "Travel", "url": "https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/27", "node": "27"},
]

# 2. Key Amazon Chart Sections
DEFAULT_CHARTS = [
    {"name": "Books - Hot New Releases", "url": "https://www.amazon.com/gp/new-releases/books", "node": "new_releases"},
    {"name": "Books - Movers & Shakers", "url": "https://www.amazon.com/gp/movers-and-shakers/books", "node": "movers_shakers"},
    {"name": "Books - Most Wished For", "url": "https://www.amazon.com/gp/most-wished-for/books", "node": "most_wished"},
]

# 3. High-Volume Search Keywords across all major literary, scientific, and professional domains
DEFAULT_SEARCH_KEYWORDS = [
    # Fiction & Literature
    "fiction novel", "nonfiction", "mystery thriller", "psychological thriller",
    "science fiction", "space opera", "epic fantasy", "dark fantasy", "urban fantasy",
    "detective mystery", "cozy mystery", "crime fiction", "historical fiction",
    "horror thriller", "short stories collection", "literary fiction", "dystopian novels",
    "contemporary romance", "dark romance", "historical romance", "poetry collection",
    "classic literature", "manga comic", "graphic novel", "mythology folklore",
    "fairy tales", "childrens picture books", "middle grade fiction", "teen young adult fantasy",
    # History, Biography & Social Sciences
    "biography memoir", "autobiography", "world history", "ancient history",
    "military history", "american history", "european history", "asian history",
    "politics government", "sociology culture", "anthropology archaeology",
    "philosophy ethics", "stoicism", "education pedagogy", "linguistics language learning",
    # STEM & Computer Science
    "computer science", "python programming", "artificial intelligence machine learning",
    "deep learning neural networks", "data science analytics", "cybersecurity ethical hacking",
    "software architecture", "web development javascript", "cloud computing devops",
    "algorithms data structures", "robotics automation", "game development unity",
    "physics mathematics", "astrophysics quantum", "biology genetics", "astronomy cosmos",
    "chemistry", "neuroscience brain", "microbiology",
    # Business, Finance & Law
    "business management", "leadership strategy", "entrepreneurship startup",
    "personal finance investing", "stock market trading", "real estate investing",
    "economics macroeconomics", "accounting auditing", "project management agile",
    "law legal studies",
    # Health, Well-being & Practical Arts
    "psychology cognitive", "self help productivity", "habits personal development",
    "mental health mindfulness", "yoga meditation", "spirituality religion",
    "cookbooks recipes", "baking desserts", "healthy nutrition diet", "fitness exercise",
    "fine arts photography", "architecture design", "creative writing guide",
    "music theory history", "travel guides", "nature wildlife", "gardening plants"
]

# 4. Publication Year Partitioning Seeds (captures books by eras and specific recent years)
YEAR_KEYWORDS = [
    "books 2026", "books 2025", "books 2024", "books 2023", "books 2022",
    "books 2021", "books 2020", "books 2019", "books 2018", "books 2017",
    "books 2016", "books 2015", "books 2010s", "books 2000s", "books 1990s",
    "vintage classic 20th century", "classic 19th century literature"
]

# 5. High-Frequency Title Words, Bigrams & Broad Dictionary Search Seeds
BIGRAM_DICTIONARY_KEYWORDS = [
    "guide handbook", "encyclopedia companion", "chronicles volume", "essential manual",
    "untold secrets", "lost kingdom", "dark empire", "eternal shadow", "journey discovery",
    "hidden truth", "magic fantasy", "mastering complete", "introduction to",
    "advanced practical", "modern approaches", "foundations principles", "ultimate collection",
    "greatest illustrated", "anthology collected works", "biographical historical",
    "scientific research", "philosophical inquiry", "mathematical thinking",
    "world civilizations", "global affairs", "human condition", "future frontiers",
    "adventures tales", "legends myths", "mysteries explored", "practical solutions"
]

COMBINED_EXPANDED_KEYWORDS = DEFAULT_SEARCH_KEYWORDS + YEAR_KEYWORDS + BIGRAM_DICTIONARY_KEYWORDS

RAW_CATEGORIES_FILE = RAW_DIR / "Amazon_All_Categories.csv"
RAW_SUBCATEGORIES_FILE = RAW_DIR / "Amazon_Discovered_Subcategories.csv"
PROCESSED_BOOKS_FILE = PROCESSED_DIR / "Amazon_Category_Books_Data.csv"
STATE_PROGRESS_FILE = STATE_DIR / "scraping_progress_categories.txt"


def is_blocked_page(html_text: str) -> bool:
    if not html_text:
        return False
    lower = html_text.lower()
    for indicator in BLOCK_INDICATORS:
        if indicator in lower:
            return True
    return False


def normalize_text(value):
    if pd.isna(value):
        return np.nan

    text_value = str(value)
    text_value = text_value.replace('"', "").replace("'", "")
    text_value = text_value.replace("“", "").replace("”", "")
    text_value = re.sub(r"\s+", " ", text_value).strip()

    if text_value.lower() in INVALID_TEXTS:
        return np.nan
    return text_value


def clean_dollar_price(val) -> str:
    """Format and guarantee dollar sign ($) in prices to prevent confusion with BDT."""
    if pd.isna(val) or val is None:
        return "$0.00"
    val_str = str(val).strip()
    if val_str == "" or val_str.lower() in ["nan", "none", "n/a", "0", "$0"]:
        return "$0.00"

    # Match standard decimal price like $24.99 or 24.99
    match = re.search(r"\$?([0-9]+(?:\.[0-9]{1,2})?)", val_str)
    if match:
        try:
            num = float(match.group(1))
            return f"${num:.2f}"
        except ValueError:
            pass

    # Match concatenated whole and cents (e.g., $3700 for $37.00 from Amazon badges)
    match_concat = re.search(r"\$?([0-9]{1,4})([0-9]{2})$", val_str)
    if match_concat:
        try:
            num = float(f"{match_concat.group(1)}.{match_concat.group(2)}")
            return f"${num:.2f}"
        except ValueError:
            pass

    return "$0.00"


def clean_review_count(val) -> int:
    """Safely converts review count formats like (207.2K), 13.3K, 1,234, 507 to integer."""
    if pd.isna(val) or val is None:
        return 0
    s = str(val).strip().replace("(", "").replace(")", "").replace(",", "").upper()
    m = re.search(r"(\d+(?:\.\d+)?)\s*([KM])?", s)
    if m:
        try:
            num = float(m.group(1))
            unit = m.group(2)
            if unit == "K":
                return int(num * 1000)
            elif unit == "M":
                return int(num * 1000000)
            return int(num)
        except ValueError:
            return 0
    return 0


def atomic_replace(src_path, dest_path, retries=3, delay=0.2):
    src = Path(str(src_path))
    dest = Path(str(dest_path))
    last_exc = None
    for _ in range(retries):
        try:
            os.replace(str(src), str(dest))
            return
        except PermissionError as exc:
            last_exc = exc
            try:
                if dest.exists():
                    os.remove(str(dest))
            except Exception:
                time.sleep(delay)
                continue
            try:
                os.replace(str(src), str(dest))
                return
            except Exception as exc2:
                last_exc = exc2
                time.sleep(delay)
                continue
        except Exception as exc:
            last_exc = exc
            time.sleep(delay)
            continue
    if last_exc:
        raise last_exc


def read_progress(path):
    if not path.exists():
        return None
    try:
        text_content = path.read_text(encoding="utf-8").strip()
        if not text_content:
            return None
        return json.loads(text_content)
    except Exception:
        return None


def write_progress(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False)
    atomic_replace(tmp, path)


def load_existing_processed(path):
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def setup_raw_categories(force=False):
    if RAW_CATEGORIES_FILE.exists() and not force:
        print(f"[SKIP] {RAW_CATEGORIES_FILE.name} already exists.")
        return pd.read_csv(RAW_CATEGORIES_FILE, low_memory=False)

    df = pd.DataFrame(DEFAULT_CATEGORIES)
    df.insert(0, "category_id", df.index + 1)
    df.rename(columns={"name": "category_name", "url": "category_url"}, inplace=True)
    tmp_out = RAW_CATEGORIES_FILE.with_suffix(RAW_CATEGORIES_FILE.suffix + ".tmp")
    df.to_csv(tmp_out, index=False, encoding="utf-8-sig")
    atomic_replace(tmp_out, RAW_CATEGORIES_FILE)
    print(f"[OK] Created {RAW_CATEGORIES_FILE.name} with {len(df)} Amazon book categories.")
    return df


def discover_subcategories_on_page(page, parent_name=""):
    """Extract nested subcategory links from the Amazon Best Sellers sidebar navigation."""
    subcats = []
    links = page.query_selector_all("div[role='treeitem'] a, div[role='group'] a, div[class*='zg-browse-group'] a, a[href*='/zgbs/books/']")
    seen_urls = set()
    for link in links:
        try:
            href = link.get_attribute("href")
            text = (link.inner_text() or "").strip()
            if not href or not text:
                continue
            if text in ["Books", "Any Department", "Department"]:
                continue
            if "/zgbs/books/" not in href:
                continue

            clean_url = href.split("?")[0].split("#")[0].split("/ref=")[0]
            if not clean_url.startswith("http"):
                clean_url = f"{DOMAIN}{clean_url}"

            node_match = re.search(r"/zgbs/books/(\d+)", clean_url)
            node = node_match.group(1) if node_match else clean_url.rstrip("/").split("/")[-1]

            if clean_url not in seen_urls:
                seen_urls.add(clean_url)
                sub_name = f"{parent_name} - {text}" if parent_name and text != parent_name else text
                subcats.append({"name": sub_name, "url": clean_url, "node": node})
        except Exception:
            continue
    return subcats


def parse_amazon_faceout_item(item_element, category_name="General"):
    """Parse faceout cards used in Best Sellers, Charts, and Subcategory pages."""
    img_el = item_element.query_selector("img[alt]")
    title = (img_el.get_attribute("alt") or "").strip() if img_el else None

    txt = item_element.inner_text()
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    if not lines:
        return None

    content_lines = []
    for l in lines:
        if re.match(r"^#?\d+$", l):
            continue
        content_lines.append(l)

    if not content_lines:
        return None

    if not title:
        title = content_lines[0]

    author = "Unknown Author"
    rating = None
    reviews = None
    book_format = "Paperback"
    price_val = None

    for i, line in enumerate(content_lines):
        if (line == title or line in title) and i + 1 < len(content_lines):
            cand_author = content_lines[i + 1]
            if not any(k in cand_author.lower() for k in ["stars", "offers", "formats", "available", "shipping", "prime", "$"]):
                author = cand_author

        if "out of 5 stars" in line:
            m = re.search(r"(\d+(?:\.\d+)?)", line)
            if m:
                rating = float(m.group(1))
        elif ("(" in line and ")" in line) or re.search(r"^[0-9,]+(\.[0-9]+)?[KM]?$", line.replace(" ", "").strip()):
            cand_rev = clean_review_count(line)
            if cand_rev > 0 and reviews is None:
                reviews = cand_rev
        elif line in ["Hardcover", "Paperback", "Kindle", "Mass Market Paperback", "Audiobook", "Audible Audiobook", "Spiral-bound", "Board book"]:
            book_format = line
        elif "$" in line and price_val is None:
            price_val = line
        elif author == "Unknown Author" and not any(k in line.lower() for k in ["stars", "offers", "formats", "available", "shipping", "prime", "$", "book"]):
            author = line

    # Extract Link and ASIN
    link_el = item_element.query_selector('a[href*="/dp/"]')
    asin = None
    book_url = None
    if link_el:
        href = link_el.get_attribute("href")
        if href:
            asin_match = re.search(r"/dp/([A-Z0-9]{10})", href)
            if asin_match:
                asin = asin_match.group(1)
                book_url = f"https://www.amazon.com/dp/{asin}"

    if not asin or not title:
        return None

    clean_price_str = clean_dollar_price(price_val)
    return {
        "asin": asin,
        "book_name": title,
        "author_name": author,
        "publisher_name": "Amazon Publishing / Trade",
        "category_name": category_name,
        "format": book_format,
        "rating": rating if rating is not None else 4.5,
        "review_count": reviews if reviews is not None else 0,
        "main_price": clean_price_str,
        "amazon_price": clean_price_str,
        "currency": "USD",
        "book_url": book_url,
    }


def parse_amazon_search_item(item_element, category_name="General"):
    """Parse search result item cards (div[data-component-type='s-search-result'])."""
    asin = item_element.get_attribute("data-asin")
    if not asin:
        return None

    h2 = item_element.query_selector("h2")
    if not h2:
        return None
    title = (h2.inner_text() or "").strip()
    if not title:
        return None

    # Author
    author = "Unknown Author"
    author_el = item_element.query_selector("div.a-row.a-size-base.a-color-secondary, .a-row .a-size-base+ .a-size-base")
    if author_el:
        txt = (author_el.inner_text() or "").strip()
        m = re.search(r"by\s+([A-Za-z0-9\.\s\-\']+)", txt, re.IGNORECASE)
        if m:
            author = m.group(1).split("|")[0].split("\n")[0].strip()
        elif txt and not any(k in txt.lower() for k in ["stars", "offers", "shipping", "prime", "$", "format"]):
            cand = txt.split("|")[0].replace("by", "").strip()
            if cand:
                author = cand

    # Format
    full_text = item_element.inner_text() or ""
    book_format = "Paperback"
    for fmt_cand in ["Kindle", "Hardcover", "Paperback", "Mass Market Paperback", "Audiobook", "Spiral-bound", "Board book"]:
        if fmt_cand.lower() in full_text.lower():
            book_format = fmt_cand
            break

    # Price
    price_val = None
    price_el = item_element.query_selector("span.a-price span.a-offscreen")
    if price_el:
        price_val = price_el.inner_text().strip()
    else:
        whole_el = item_element.query_selector("span.a-price-whole")
        frac_el = item_element.query_selector("span.a-price-fraction")
        if whole_el:
            w = whole_el.inner_text().strip().replace(".", "")
            f = frac_el.inner_text().strip() if frac_el else "00"
            price_val = f"${w}.{f}"

    clean_price_str = clean_dollar_price(price_val)

    # Rating
    rating = 4.5
    rating_el = item_element.query_selector("i.a-icon-star-small span, i.a-icon-star span, .a-icon-alt")
    if rating_el:
        rtxt = rating_el.inner_text().strip()
        m_rate = re.search(r"(\d+(?:\.\d+)?)", rtxt)
        if m_rate:
            try:
                rating = float(m_rate.group(1))
            except ValueError:
                pass

    # Reviews
    reviews = 0
    reviews_el = item_element.query_selector("a[href*='customerReviews'] span, span.s-underline-text")
    if reviews_el:
        reviews = clean_review_count(reviews_el.inner_text().strip())

    book_url = f"https://www.amazon.com/dp/{asin}"
    return {
        "asin": asin,
        "book_name": title,
        "author_name": author,
        "publisher_name": "Amazon Publishing / Trade",
        "category_name": category_name,
        "format": book_format,
        "rating": rating,
        "review_count": reviews,
        "main_price": clean_price_str,
        "amazon_price": clean_price_str,
        "currency": "USD",
        "book_url": book_url,
    }


def scrape_amazon_pipeline(
    mode="all",
    max_pages=2,
    discover_subcategories=False,
    include_charts=False,
    search_keywords=None,
    category_limit=None,
):
    """
    Unified crawler supporting:
    1. Main Departments Bestsellers
    2. Deep Subcategories Auto-Discovery
    3. Charts (New Releases, Movers & Shakers, Most Wished For)
    4. Keyword Search Listings Pagination
    """
    categories_df = setup_raw_categories()
    existing_df = load_existing_processed(PROCESSED_BOOKS_FILE)
    all_books = existing_df.to_dict("records") if not existing_df.empty else []
    seen_asins = {row["asin"] for row in all_books if "asin" in row and pd.notna(row["asin"])}

    progress = read_progress(STATE_PROGRESS_FILE)
    resume_target = progress.get("target") if progress else None

    # Build queue of targets based on mode
    targets = []

    # 1. Main Best Sellers Categories
    if mode in ["all", "bestsellers"]:
        for _, cat in categories_df.iterrows():
            targets.append({
                "type": "bestseller",
                "name": cat["category_name"],
                "url": cat["category_url"],
                "node": cat.get("node", ""),
            })

    # 2. Charts (Hot New Releases, Movers & Shakers, Most Wished For)
    if mode in ["all", "charts"] or include_charts:
        for chart in DEFAULT_CHARTS:
            targets.append({
                "type": "chart",
                "name": chart["name"],
                "url": chart["url"],
                "node": chart["node"],
            })

    # 3. Search Keywords
    if mode in ["all", "search"] or search_keywords:
        kws = search_keywords if search_keywords else DEFAULT_SEARCH_KEYWORDS
        for kw in kws:
            kw_clean = kw.strip()
            if kw_clean:
                search_url = f"https://www.amazon.com/s?i=stripbooks&k={kw_clean.replace(' ', '+')}"
                targets.append({
                    "type": "search",
                    "name": f"Search: {kw_clean.title()}",
                    "url": search_url,
                    "keyword": kw_clean,
                })

    if category_limit and category_limit > 0:
        targets = targets[:category_limit]

    print(f"[SCRAPE] Starting Amazon books multi-source crawler. Total queue size: {len(targets)} targets.")
    print(f"[SCRAPE] Currently have {len(seen_asins)} unique books in database.")

    discovered_subcategories_list = []
    target_names = {t["name"] for t in targets}
    resume_found = (resume_target is None) or (resume_target not in target_names)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        idx = 0
        while idx < len(targets):
            item = targets[idx]
            target_type = item["type"]
            t_name = item["name"]
            t_url = item["url"]
            idx += 1

            if not resume_found:
                if t_name == resume_target:
                    resume_found = True
                else:
                    continue

            print(f"\n[CRAWL] [{idx}/{len(targets)}] ({target_type.upper()}) {t_name}")
            print(f" -> URL: {t_url}")

            for page_num in range(1, max_pages + 1):
                if target_type == "search":
                    page_url = f"{t_url}&page={page_num}" if page_num > 1 else t_url
                else:
                    page_url = f"{t_url}?pg={page_num}" if page_num > 1 else t_url

                try:
                    page.goto(page_url, wait_until="domcontentloaded", timeout=40000)
                    time.sleep(random.uniform(1.5, 3.0))

                    content = page.content()
                    if is_blocked_page(content):
                        print(f"[BLOCKED] Amazon bot check detected on '{t_name}' pg {page_num}. Saving state and stopping.")
                        write_progress(STATE_PROGRESS_FILE, {"target": t_name, "page": page_num})
                        browser.close()
                        return

                    # Dynamic subcategories discovery (from sidebar on page 1 of bestsellers and subcategories)
                    if discover_subcategories and target_type in ["bestseller", "subcategory"] and page_num == 1 and len(targets) < 800:
                        subcats = discover_subcategories_on_page(page, parent_name=t_name)
                        new_subcats = [s for s in subcats if not any(t["url"] == s["url"] for t in targets)]
                        if new_subcats:
                            print(f"  [DISCOVERY] Found {len(new_subcats)} subcategories under '{t_name}'")
                            for s in new_subcats:
                                s_entry = {
                                    "type": "subcategory",
                                    "name": s["name"],
                                    "url": s["url"],
                                    "node": s["node"],
                                }
                                targets.append(s_entry)
                                discovered_subcategories_list.append(s)

                    # Extract books based on target type
                    if target_type == "search":
                        items = page.query_selector_all("div[data-component-type='s-search-result']")
                        print(f" -> Page {page_num}: found {len(items)} search items")
                        if not items:
                            break
                        added_for_page = 0
                        clean_cat = t_name.replace("Search: ", "") if t_name.startswith("Search: ") else t_name
                        for card in items:
                            parsed = parse_amazon_search_item(card, category_name=clean_cat)
                            if parsed and parsed["asin"] not in seen_asins:
                                all_books.append(parsed)
                                seen_asins.add(parsed["asin"])
                                added_for_page += 1
                        print(f" -> Added {added_for_page} new books (Total unique: {len(seen_asins)})")

                        # End-of-results detection ("end porjonto scrape")
                        disabled_next = page.query_selector("span.s-pagination-disabled.s-pagination-next, li.a-disabled.a-last")
                        if disabled_next:
                            print(f" -> Reached last available page for '{t_name}'.")
                            break

                    else:
                        items = page.query_selector_all("div.zg-grid-general-faceout")
                        if not items:
                            items = page.query_selector_all("div[id*='gridItemRoot']")
                        print(f" -> Page {page_num}: found {len(items)} chart items")
                        if not items:
                            break
                        added_for_page = 0
                        for card in items:
                            parsed = parse_amazon_faceout_item(card, category_name=t_name)
                            if parsed and parsed["asin"] not in seen_asins:
                                all_books.append(parsed)
                                seen_asins.add(parsed["asin"])
                                added_for_page += 1
                        print(f" -> Added {added_for_page} new books (Total unique: {len(seen_asins)})")

                except Exception as exc:
                    print(f"[WARN] Error on '{t_name}' page {page_num}: {exc}")
                    break

            # Save progress atomically after each target
            tmp_out = PROCESSED_BOOKS_FILE.with_suffix(PROCESSED_BOOKS_FILE.suffix + ".tmp")
            pd.DataFrame(all_books).to_csv(tmp_out, index=False, encoding="utf-8-sig")
            atomic_replace(tmp_out, PROCESSED_BOOKS_FILE)
            write_progress(STATE_PROGRESS_FILE, {"target": t_name, "page": None})

            # Record discovered subcategories if any
            if discovered_subcategories_list:
                try:
                    disc_df = pd.DataFrame(discovered_subcategories_list).drop_duplicates(subset=["url"])
                    disc_tmp = RAW_SUBCATEGORIES_FILE.with_suffix(RAW_SUBCATEGORIES_FILE.suffix + ".tmp")
                    disc_df.to_csv(disc_tmp, index=False, encoding="utf-8-sig")
                    atomic_replace(disc_tmp, RAW_SUBCATEGORIES_FILE)
                except Exception:
                    pass

        browser.close()

    print(f"\n[SCRAPE COMPLETED] Total books collected in catalog: {len(all_books)}")


def build_clean_csvs():
    print("[BUILD] Loading and normalizing Amazon books dataset...")
    if not PROCESSED_BOOKS_FILE.exists():
        raise FileNotFoundError(f"Missing {PROCESSED_BOOKS_FILE}. Please run with --scrape or supply raw data.")

    df = pd.read_csv(PROCESSED_BOOKS_FILE, low_memory=False)

    # Normalize texts
    for col in ["book_name", "author_name", "publisher_name", "category_name"]:
        if col in df.columns:
            df[col] = df[col].map(normalize_text)

    df["book_name"] = df["book_name"].fillna("Unknown Book")
    df["author_name"] = df["author_name"].fillna("Unknown Author")
    df["publisher_name"] = df["publisher_name"].fillna("Amazon Publishing / Trade")
    df["category_name"] = df["category_name"].fillna("General Books")

    # Ensure Dollar Sign ($) in prices
    df["main_price"] = df["main_price"].apply(clean_dollar_price)
    df["amazon_price"] = df["amazon_price"].apply(clean_dollar_price)
    df["currency"] = "USD"

    # Ensure format and reviews
    if "review_count" in df.columns:
        df["review_count"] = df["review_count"].apply(clean_review_count)
    else:
        df["review_count"] = 0

    if "rating" in df.columns:
        df["rating"] = pd.to_numeric(df["rating"], errors="coerce").fillna(4.5)
    else:
        df["rating"] = 4.5

    # Save all_scraped_book_rows
    for path in [PROJECT_DIR / "all_scraped_book_rows.csv", PROCESSED_DIR / "all_scraped_book_rows.csv"]:
        df.to_csv(path, index=False, encoding="utf-8-sig")

    # 1. Categories Table
    unique_cats = df["category_name"].dropna().unique()
    categories = pd.DataFrame({"category_name": unique_cats})
    categories.insert(0, "category_id", categories.index + 1)

    # 2. Authors Table
    unique_authors = df["author_name"].dropna().unique()
    authors = pd.DataFrame({"author_name": unique_authors})
    authors["profile_link"] = authors["author_name"].apply(lambda n: f"https://www.amazon.com/s?k={n.replace(' ', '+')}&i=stripbooks")
    authors.insert(0, "author_id", authors.index + 1)

    # 3. Publishers Table
    unique_publishers = df["publisher_name"].dropna().unique()
    publishers = pd.DataFrame({"publisher_name": unique_publishers})
    publishers.insert(0, "publisher_id", publishers.index + 1)

    # 4. Books Table (Relational)
    books = df.merge(authors, on="author_name", how="left") \
              .merge(publishers, on="publisher_name", how="left") \
              .merge(categories, on="category_name", how="left")

    books["author_id"] = books["author_id"].fillna(1).astype(int)
    books["publisher_id"] = books["publisher_id"].fillna(1).astype(int)
    books["category_id"] = books["category_id"].fillna(1).astype(int)

    books = books[["asin", "book_name", "author_id", "publisher_id", "category_id", "main_price", "amazon_price", "currency", "format", "rating", "review_count", "book_url"]].drop_duplicates(subset=["asin"]).reset_index(drop=True)
    books.insert(0, "book_id", books.index + 1)

    # Write clean tables to root and processed
    outputs = {
        "clean_categories.csv": categories,
        "clean_authors.csv": authors,
        "clean_publishers.csv": publishers,
        "clean_books.csv": books,
    }
    for filename, table_df in outputs.items():
        root_path = PROJECT_DIR / filename
        processed_path = PROCESSED_DIR / filename
        table_df.to_csv(root_path, index=False, encoding="utf-8-sig")
        shutil.copyfile(root_path, processed_path)
        print(f"[OK] {filename}: {len(table_df)} rows")

    # 5. Master Table (Denormalized)
    master = books.merge(authors[["author_id", "author_name"]], on="author_id", how="left") \
                  .merge(publishers[["publisher_id", "publisher_name"]], on="publisher_id", how="left") \
                  .merge(categories[["category_id", "category_name"]], on="category_id", how="left")

    master = master[["book_id", "asin", "book_name", "author_id", "author_name", "publisher_id", "publisher_name", "category_id", "category_name", "main_price", "amazon_price", "currency", "format", "rating", "review_count", "book_url"]]

    for path in [PROJECT_DIR / "master.csv", PROCESSED_DIR / "master.csv"]:
        master.to_csv(path, index=False, encoding="utf-8-sig")

    print(f"[OK] master.csv: {len(master)} rows (all prices formatted with '$' USD)")
    return categories, authors, publishers, books, master


def upload_sql(categories, authors, publishers, books):
    print("[SQL] Connecting and rebuilding Amazon database tables in MySQL...")
    server_uri = f"mysql+mysqlconnector://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}"
    base_engine = create_engine(server_uri)
    with base_engine.begin() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}"))

    database_uri = f"mysql+mysqlconnector://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(database_uri)

    with engine.begin() as conn:
        existing_objects = conn.execute(text("SHOW FULL TABLES")).fetchall()
        for row in existing_objects:
            object_name = row[0]
            object_type = str(row[1]).upper()
            escaped_name = str(object_name).replace("`", "``")
            if object_type == "VIEW":
                conn.execute(text(f"DROP VIEW IF EXISTS `{escaped_name}`"))
            else:
                conn.execute(text(f"DROP TABLE IF EXISTS `{escaped_name}`"))

    categories.to_sql("categories", con=engine, if_exists="replace", index=False)
    authors.to_sql("authors", con=engine, if_exists="replace", index=False)
    publishers.to_sql("publishers", con=engine, if_exists="replace", index=False)
    books.to_sql("books", con=engine, if_exists="replace", index=False)

    master_query = """
        CREATE TABLE master AS
        SELECT
            b.book_id,
            b.asin,
            b.book_name,
            b.author_id,
            a.author_name,
            b.publisher_id,
            p.publisher_name,
            b.category_id,
            c.category_name,
            b.main_price,
            b.amazon_price,
            b.currency,
            b.format,
            b.rating,
            b.review_count,
            b.book_url
        FROM books b
        LEFT JOIN authors a ON b.author_id = a.author_id
        LEFT JOIN publishers p ON b.publisher_id = p.publisher_id
        LEFT JOIN categories c ON b.category_id = c.category_id
    """
    with engine.begin() as conn:
        conn.execute(text(master_query))

    master_df = pd.read_sql(text("SELECT * FROM master ORDER BY book_id"), con=engine)
    print(f"[SQL] Created tables in {DB_NAME}: categories, authors, publishers, books, master ({len(master_df)} rows)")


def verify_local_csvs():
    print("==================================================")
    print("AMAZON DATA INTEGRITY & PRICE DOLLAR VERIFICATION")
    print("==================================================")
    for name in ["clean_categories.csv", "clean_authors.csv", "clean_publishers.csv", "clean_books.csv", "master.csv"]:
        p = PROJECT_DIR / name
        if not p.exists():
            print(f"[FAIL] Missing {name}")
            return False

    categories = pd.read_csv(PROJECT_DIR / "clean_categories.csv")
    authors = pd.read_csv(PROJECT_DIR / "clean_authors.csv")
    publishers = pd.read_csv(PROJECT_DIR / "clean_publishers.csv")
    books = pd.read_csv(PROJECT_DIR / "clean_books.csv")
    master = pd.read_csv(PROJECT_DIR / "master.csv")

    print(f"Categories: {len(categories):,}")
    print(f"Authors: {len(authors):,}")
    print(f"Publishers: {len(publishers):,}")
    print(f"Books: {len(books):,}")
    print(f"Master Catalog: {len(master):,}")

    orphan_authors = (~books["author_id"].isin(authors["author_id"])).sum()
    orphan_publishers = (~books["publisher_id"].isin(publishers["publisher_id"])).sum()
    orphan_categories = (~books["category_id"].isin(categories["category_id"])).sum()

    print(f"Orphan author FKs: {orphan_authors}")
    print(f"Orphan publisher FKs: {orphan_publishers}")
    print(f"Orphan category FKs: {orphan_categories}")

    has_dollar_main = master["main_price"].astype(str).str.startswith("$").sum()
    has_dollar_amazon = master["amazon_price"].astype(str).str.startswith("$").sum()
    print(f"Main prices with '$' sign: {has_dollar_main:,} / {len(master):,}")
    print(f"Amazon prices with '$' sign: {has_dollar_amazon:,} / {len(master):,}")
    print(f"Currencies set to USD: {(master['currency'] == 'USD').sum():,} / {len(master):,}")

    print("Sample Master Rows:")
    for _, r in master.head(3).iterrows():
        print(f" -> [{r['asin']}] '{r['book_name']}' by {r['author_name']} | Price: {r['amazon_price']} USD | Rating: {r['rating']}⭐")

    print("==================================================")
    return orphan_authors == 0 and orphan_publishers == 0 and orphan_categories == 0


def main():
    parser = argparse.ArgumentParser(description="Unified Amazon Books Scraper, Normalization & SQL Pipeline.")
    parser.add_argument("--scrape", action="store_true", help="Scrape Amazon books.")
    parser.add_argument("--scrape-all", action="store_true", help="Scrape Bestsellers, Discovered Subcategories, Charts, and Search listings.")
    parser.add_argument("--deep-expansion", action="store_true", help="Maximum scale: 7 pages per query, A-Z/Bigram/Dictionary seeds, Publication Years, deep nested subcategories, and charts.")
    parser.add_argument("--mode", choices=["all", "bestsellers", "charts", "search"], default=None, help="Target specific scrape mode.")
    parser.add_argument("--discover-subcategories", action="store_true", help="Discover and scrape nested subcategories from the sidebar.")
    parser.add_argument("--include-charts", action="store_true", help="Include New Releases, Movers & Shakers, and Most Wished For.")
    parser.add_argument("--search-keywords", type=str, nargs="?", const="", default=None, help="Comma-separated keywords to search (e.g. 'python, thriller, fantasy').")
    parser.add_argument("--max-pages", type=int, default=2, help="Number of pages to scrape per category or keyword (default: 2; deep expansion defaults to 7).")
    parser.add_argument("--category-limit", type=int, default=None, help="Limit number of target categories/searches.")
    parser.add_argument("--force-list", action="store_true", help="Re-seed raw categories list.")
    parser.add_argument("--build-only", action="store_true", help="Build clean CSVs without scraping or SQL upload.")
    parser.add_argument("--verify-only", action="store_true", help="Verify clean CSVs and dollar pricing.")
    args = parser.parse_args()

    if args.force_list and not (args.scrape or args.scrape_all or args.deep_expansion or args.build_only or args.mode or args.search_keywords):
        setup_raw_categories(force=True)
        print("[OK] Categories list refreshed.")
        return

    if args.force_list:
        setup_raw_categories(force=True)

    if args.verify_only:
        verify_local_csvs()
        return

    should_scrape = args.scrape or args.scrape_all or args.deep_expansion or (args.mode is not None) or (args.search_keywords is not None)

    if should_scrape:
        if args.deep_expansion:
            selected_mode = "all"
            discover_subs = True
            inc_charts = True
            keywords = COMBINED_EXPANDED_KEYWORDS
            effective_max_pages = 7 if args.max_pages == 2 else args.max_pages
        else:
            discover_subs = args.discover_subcategories or args.scrape_all
            inc_charts = args.include_charts or args.scrape_all
            effective_max_pages = args.max_pages

            if args.mode:
                selected_mode = args.mode
            elif args.scrape_all:
                selected_mode = "all"
            elif args.search_keywords is not None and not args.scrape:
                selected_mode = "search"
            else:
                selected_mode = "bestsellers"

            keywords = None
            if args.search_keywords is not None:
                if args.search_keywords.strip():
                    keywords = [k.strip() for k in args.search_keywords.split(",") if k.strip()]
                else:
                    keywords = DEFAULT_SEARCH_KEYWORDS
            elif selected_mode in ["all", "search"]:
                keywords = DEFAULT_SEARCH_KEYWORDS

        scrape_amazon_pipeline(
            mode=selected_mode,
            max_pages=effective_max_pages,
            discover_subcategories=discover_subs,
            include_charts=inc_charts,
            search_keywords=keywords,
            category_limit=args.category_limit,
        )

    cats, auths, pubs, books, master = build_clean_csvs()
    verify_local_csvs()

    if not args.build_only:
        try:
            upload_sql(cats, auths, pubs, books)
        except Exception as exc:
            print(f"[SQL WARNING] Database upload skipped or failed: {exc}")

    print("[DONE] Amazon pipeline completed successfully.")


if __name__ == "__main__":
    main()
