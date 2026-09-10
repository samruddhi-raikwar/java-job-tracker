import csv
import hashlib
import html
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CSV_FILE = Path("data/job_tracker.csv")

# Search engines are used only to discover individual job-posting pages.
# The tracker rejects generic search/list pages and keeps direct job URLs.
SEARCHES = [
    'site:linkedin.com/jobs/view Java Developer Hyderabad fresher',
    'site:linkedin.com/jobs/view Java Full Stack Developer Hyderabad',
    'site:in.indeed.com/viewjob Java Developer Hyderabad fresher',
    'site:in.indeed.com/viewjob Java Full Stack Developer Hyderabad',
    'site:naukri.com/job-listings Java Developer Hyderabad fresher',
    'site:foundit.in/job Java Developer Hyderabad fresher',
    'site:hirist.tech Java Developer Hyderabad 0-2 years',
    'site:internshala.com/job/detail Java Developer Hyderabad fresher',
    'site:shine.com/jobs Java Developer Hyderabad fresher',
]

ALLOWED_DOMAINS = [
    "linkedin.com", "indeed.com", "naukri.com", "foundit.in",
    "hirist.tech", "internshala.com", "shine.com", "glassdoor.co.in",
    "jooble.org", "simplyhired.co.in"
]

LOCATION_KEYWORDS = ["hyderabad", "secunderabad"]
ENTRY_KEYWORDS = [
    "fresher", "freshers", "entry level", "entry-level", "0-1", "0-2",
    "0–1", "0–2", "junior", "trainee", "graduate", "associate", "intern",
    "early career", "0 to 1", "0 to 2", "1 year", "2 years"
]
SENIOR_KEYWORDS = [
    "5+ years", "6+ years", "7+ years", "8+ years", "10+ years",
    "5 years experience", "6 years experience", "7 years experience",
    "8 years experience", "10 years experience", "senior manager",
    "principal engineer", "architect", "tech lead", "technical lead"
]
BAD_PAGE_WORDS = [
    "/jobs-in-", "/job-search", "/search", "/jobs?", "/jobs/", "/job-search/",
    "search?q=", "fresher-jobs-in", "jobs-in-hyderabad", "job-search"
]


def fetch_search(query):
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36"
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="ignore")


def clean_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def domain_of(url):
    host = urllib.parse.urlparse(url).netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def allowed_domain(url):
    host = domain_of(url)
    return any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)


def is_search_page(url):
    lower = url.lower()
    return any(word in lower for word in BAD_PAGE_WORDS)


def parse_results(page):
    results = []
    # DuckDuckGo HTML result blocks.
    blocks = re.findall(r'<div[^>]+class="result[^>]*>(.*?)</div>\s*</div>', page, flags=re.I | re.S)
    if not blocks:
        blocks = re.findall(r'<div[^>]+class="result[^>]*>(.*?)(?=<div[^>]+class="result|$)', page, flags=re.I | re.S)

    for block in blocks:
        match = re.search(r'class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.I | re.S)
        if not match:
            continue
        url = html.unescape(match.group(1))
        title = clean_text(match.group(2))
        if "uddg=" in url:
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            url = parsed.get("uddg", [url])[0]
        if not url.startswith("http") or not allowed_domain(url) or is_search_page(url):
            continue
        snippet_match = re.search(r'class="result__snippet"[^>]*>(.*?)</(?:a|div)>', block, flags=re.I | re.S)
        snippet = clean_text(snippet_match.group(1)) if snippet_match else clean_text(block)
        results.append({"title": title, "url": url, "snippet": snippet})

    return results


def extract_experience(text):
    t = text.lower()
    patterns = [
        r"\b(0\s*[-–]\s*[12]\s*years?)\b",
        r"\b(1\s*[-–]\s*2\s*years?)\b",
        r"\b(0\s+to\s+[12]\s*years?)\b",
        r"\b([12]\s*years?\s*(?:of\s*)?experience)\b",
        r"\b(fresher(?:s)?)\b",
        r"\b(entry[- ]level)\b",
        r"\b(junior|trainee|graduate)\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, t, re.I)
        if m:
            return m.group(1)
    return "Not disclosed"


def extract_salary(text):
    patterns = [
        r"(?:₹|rs\.?\s*)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:-|to)\s*([0-9]+(?:\.[0-9]+)?)\s*(lpa|lakhs?|lac)\b",
        r"(?:₹|rs\.?\s*)\s*([0-9]+(?:\.[0-9]+)?)\s*(lpa|lakhs?|lac)\b",
        r"\b([0-9]+(?:\.[0-9]+)?)\s*(?:-|to)\s*([0-9]+(?:\.[0-9]+)?)\s*(lpa|lakhs?|lac)\b",
        r"\b([0-9]+(?:\.[0-9]+)?)\s*(lpa|lakhs?|lac)\b",
        r"(?:₹|rs\.?\s*)\s*([0-9,]+)\s*(?:/\s*month|per\s*month|monthly)\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return clean_text(m.group(0))
    return "Not disclosed"


def extract_company(title, snippet, url):
    combined = clean_text(title)
    # Common search-result title format: Job Title - Company - Location
    parts = [p.strip() for p in re.split(r"\s+[-|–—]\s+", combined) if p.strip()]
    if len(parts) >= 2:
        candidates = [p for p in parts[1:] if not any(x in p.lower() for x in ["hyderabad", "india", "apply", "jobs"])]
        if candidates:
            return candidates[0][:100]

    # Some listings expose Company: ... in the snippet.
    m = re.search(r"(?:company|employer)\s*[:\-]\s*([^|,.]{2,80})", snippet, re.I)
    if m:
        return clean_text(m.group(1))

    # Fall back to the job-board host rather than falsely inventing a company.
    return domain_of(url)


def make_id(title, url):
    return hashlib.sha256(f"{title}|{url}".lower().encode()).hexdigest()[:16]


def load_existing():
    existing = set()
    if not CSV_FILE.exists():
        return existing
    with open(CSV_FILE, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            link = row.get("Apply Link", "").strip()
            if link:
                existing.add(link)
    return existing


def score_job(title, snippet):
    text = f"{title} {snippet}".lower()
    score = 0
    for word, points in [
        ("java", 30), ("full stack", 25), ("spring boot", 20),
        ("microservices", 10), ("rest", 7), ("react", 7),
        ("sql", 5), ("hibernate", 5), ("fresher", 20),
        ("0-1", 20), ("0-2", 20), ("junior", 15), ("trainee", 15),
        ("hyderabad", 20), ("secunderabad", 20)
    ]:
        if word in text:
            score += points
    if any(k in text for k in SENIOR_KEYWORDS):
        score -= 50
    return score


def parse_job(result):
    title = clean_text(result["title"])
    snippet = clean_text(result["snippet"])
    url = result["url"]
    text = f"{title} {snippet}".lower()

    if "java" not in text or not any(k in text for k in LOCATION_KEYWORDS):
        return None
    if any(k in text for k in SENIOR_KEYWORDS):
        return None
    if not any(k in text for k in ENTRY_KEYWORDS):
        # Allow unspecified experience only when the title is clearly a junior/trainee/fresher role.
        if not any(k in text for k in ["junior java", "java fresher", "trainee java"]):
            return None

    score = score_job(title, snippet)
    if score < 45:
        return None

    return {
        "title": title,
        "company": extract_company(title, snippet, url),
        "location": "Hyderabad, India",
        "experience": extract_experience(text),
        "salary": extract_salary(text),
        "posted": "Not disclosed",
        "source": domain_of(url),
        "url": url,
        "score": score,
    }


def append_jobs(jobs):
    CSV_FILE.parent.mkdir(parents=True, exist_ok=True)
    fields = ["Date Found", "Job Title", "Company", "Location", "Experience", "Salary", "Posted", "Source", "Apply Link"]
    existing = load_existing()
    file_exists = CSV_FILE.exists() and CSV_FILE.stat().st_size > 0
    added = 0

    with open(CSV_FILE, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not file_exists:
            writer.writeheader()
        for job in jobs:
            if job["url"] in existing:
                continue
            writer.writerow({
                "Date Found": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "Job Title": job["title"],
                "Company": job["company"],
                "Location": job["location"],
                "Experience": job["experience"],
                "Salary": job["salary"],
                "Posted": job["posted"],
                "Source": job["source"],
                "Apply Link": job["url"],
            })
            existing.add(job["url"])
            added += 1
    return added


def main():
    candidates = {}
    print("Searching for individual Hyderabad Java job postings...")

    for query in SEARCHES:
        print(f"Searching: {query}")
        try:
            page = fetch_search(query)
            results = parse_results(page)
            accepted = 0
            for result in results:
                job = parse_job(result)
                if job:
                    key = job["url"].rstrip("/")
                    if key not in candidates or job["score"] > candidates[key]["score"]:
                        candidates[key] = job
                        accepted += 1
            print(f"  Individual postings accepted: {accepted}")
        except Exception as e:
            print(f"Search failed: {e}")

    jobs = sorted(candidates.values(), key=lambda x: x["score"], reverse=True)[:25]
    added = append_jobs(jobs)
    print(f"Found {len(jobs)} individual job-posting candidates.")
    print(f"Added {added} new jobs to the tracker.")


if __name__ == "__main__":
    main()
