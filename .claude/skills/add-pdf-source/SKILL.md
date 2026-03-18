---
name: add-pdf-source
description: Add a new PDF scraping source to the fetch_pdfs framework. Use this
  skill when the user wants to scrape PDFs from a new website and add it as a source
  to the fetch_pdfs package. Covers site analysis, implementation, and registration.
argument-hint: "<source_name> <url1> [url2 ...] [--package <path>]"
---

# Add a new PDF scraping source

You are adding a new source to a PDF scraping framework.

**Arguments:** `$ARGUMENTS` contains all arguments as a single string. Parse them as follows:
- **First token** = source short name (lowercase, e.g. `fbf`)
- **All URLs** (tokens starting with `http://` or `https://`) = starting URLs to explore.
  Multiple URLs are common when a site has separate sitemaps per language
  (e.g. `/fr/plan-du-site/` and `/en/site-map/`). Explore ALL provided URLs.
- **`--package <path>`** (optional) = package path. Defaults to `scripts/vpfister/fetch_pdfs`.

Examples:
```
/add-pdf-source fbf https://www.fbf.fr/fr/plan-du-site/ https://www.fbf.fr/en/site-map/
/add-pdf-source acpr https://acpr.banque-france.fr/sitemap --package some/other/package
/add-pdf-source efama https://www.efama.org/sitemap
```

## Prerequisites

**Always** run `source .venv/bin/activate` before any Python command in every Bash call.
This applies to all inline scripts, import checks, and any `python3` invocation.

## Step 1: Explore the website

Before writing any code, thoroughly analyze the target website to understand its structure.
Use `curl` + BeautifulSoup in inline Python scripts to fetch and parse pages.

### What to discover

1. **CMS/technology**: WordPress, Drupal, custom? Check for REST APIs:
   - WordPress: `GET /wp-json/wp/v2/posts` (check if it returns JSON or redirects to HTML)
   - Drupal: `GET /jsonapi/node/<type>`
   - Look for `<meta name="Generator">` in HTML

2. **Listing pages**: where are articles/publications listed?
   - Find all sections from the sitemap/navigation
   - For each section: count articles, check for pagination

3. **Pagination mechanism**:
   - Simple URL params: `?page=N`, `?offset=N`
   - AJAX/XHR: look for `data-count`, `load-more` buttons, form actions with `ajax` in the URL
   - For AJAX: identify the endpoint, required parameters (CSRF tokens, category IDs, etc.)
   - Check `<main>` or container elements for `data-count`, `data-total` attributes

4. **Article page structure**: visit 3-5 sample articles and check:
   - Where PDF links appear (download buttons, inline links, attachment sections)
   - The CSS selector that reliably captures PDF links
   - The URL pattern for PDFs (e.g. `/uploads/YYYY/MM/*.pdf`, `/sites/default/files/*.pdf`)
   - Whether all articles have PDFs or only some
   - Category/topic metadata available on the page

5. **Languages**: discover ALL languages available on the site.
   - Check for language switchers, `hreflang` links, `/fr/` `/en/` `/de/` path prefixes, etc.
   - Determine whether translations are separate content or linked versions of the same articles
   - Check if different languages have different PDFs or share them
   - The user may provide hints about expected languages, but always verify what actually exists

6. **Overlap between sections**: if there are multiple listing sections, check if articles
   appear in more than one. Sample a few sections and measure overlap.

### Output of analysis

Write a markdown analysis document at `{package_path}/analysis_$0.md` covering:
- Site overview (CMS, languages, PDF URL pattern)
- Table of all sections with URLs, counts, and IDs (for every language found)
- Listing/pagination mechanism details
- Article page structure (HTML around PDF links)
- Implementation plan

## Step 2: Implement the source

Create `{package_path}/source_$0.py` following the existing patterns.

### Architecture reference

The framework uses a `Source` protocol defined in `common.py`:

```python
class Source(Protocol):
    name: str
    dest_dir: Path

    def scan(self, known_article_urls: set[str]) -> Iterator[IndexEntry]: ...
```

Each `IndexEntry` is a TypedDict:

```python
class IndexEntry(TypedDict):
    name: str            # filename
    path: str            # relative path under dest_dir (e.g. "category/file.pdf")
    url: str             # PDF download URL
    source_url: str | None  # article page URL (used for resumability)
    file: str | None     # local file path (set during download)
    status: str          # "scanned" | "downloading" | "downloaded" | "error" | "skipped"
```

### Common two-phase pattern

Most sources follow this pattern:

**Phase 1 — Crawl listing pages** (fast):
- Paginate through listing pages to collect all article URLs
- Progress bar with `tqdm(unit=" page", desc="Crawling listing", file=sys.stderr)`

**Phase 2 — Visit each article page** (slow):
- Skip articles already in `known_article_urls` (resumability)
- Extract category/topic metadata from the page
- Find all PDF links
- Yield one `IndexEntry` per PDF
- Progress bar with `tqdm(total=N, unit="article", desc="Scanning articles", file=sys.stderr)`
- Random sleep between requests: `time.sleep(random.uniform(1, 3))`

### Mandatory requirements

- **tqdm progress bars** on both phases for user feedback and ETA
- **Resumability**: use `known_article_urls` to skip already-processed articles
- **Polite crawling**: random delays between requests (0.5-1.5s for listing, 1-3s for articles)
- **Custom User-Agent**: `"MistralResearchBot/1.0 (PDF collection for NLP research)"`
- **Error handling**: log warnings and continue on individual article failures
- **Deduplication**: dedup PDF URLs within and across articles

### Helpers available from `common.py`

- `safe_filename(url)` — filesystem-safe filename from URL, truncated with SHA256 if too long
- `slugify(text)` — text to ASCII slug for directory names
- `normalize_url(url)` — strip fragments and query params

### File organization

PDFs go under `/mnt/vast/datasets_raw/finance-docs/$0/`. Organize by category:
- Single language: `<category-slug>/<filename>.pdf`
- Multi-language: `<lang>/<category-slug>/<filename>.pdf`

### Source dataclass template

```python
@dataclass
class XxxSource:
    name: str = "$0"
    dest_dir: Path = field(default_factory=lambda: Path("/mnt/vast/datasets_raw/finance-docs/$0"))

    def scan(self, known_article_urls: set[str]) -> Iterator[IndexEntry]:
        ...
```

## Step 3: Register the source

Edit `{package_path}/__main__.py`:
1. Add the import (keep alphabetical order)
2. Add to the `SOURCES` dict (keep alphabetical order)

Verify with: `source .venv/bin/activate && python3 -c "from {package_module}.__main__ import SOURCES; print(sorted(SOURCES.keys()))"`

(where `{package_module}` is the dotted module path derived from `{package_path}`, e.g. `scripts.vpfister.fetch_pdfs`)

## Step 4: Verify

Run import check to confirm no errors. Do NOT run the actual scan (it takes a long time).

## Existing sources for reference

| Source | File | Strategy |
|--------|------|----------|
| OFCE | `source_ofce.py` | Recursive directory crawl of Apache-style file listing |
| AMF | `source_amf.py` | JSON API for listings → article page scraping for PDFs |
| BDF | `source_bdf.py` | Paginated HTML listing → article scraping, FR+EN via hreflang |
| ISDA | `source_isda.py` | WordPress REST API pagination, PDFs from `free_downloads` field |
| EFAMA | `source_efama.py` | Simple `?page=N` HTML pagination → article scraping |
| FBF | `source_fbf.py` | AJAX POST with CSRF token for pagination → article scraping |
