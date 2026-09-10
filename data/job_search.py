import csv
import hashlib
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

CSV_FILE = Path("data/job_tracker.csv")

# Search the public web for actual job-listing pages instead of Google News.
SEARCHES = [
    'Java Developer Hyderabad fresher jobs',
    'Java Developer Hyderabad 0-2 years jobs',
    'Java Full Stack Developer Hyderabad jobs',
    'Spring Boot Java Developer Hyderabad fresher jobs',
    'Junior Java Developer Hyderabad jobs',
    'Trainee Java Developer Hyderabad jobs',
    'Java Developer Hyderabad graduate jobs',
]

JOB_SITES = [
    "indeed.com", "naukri.com", "linkedin.com/jobs", "foundit.in",
    "hirist.tech", "instahyre.com", "cutshort.io", "wellfound.com",
    "internshala.com", "shine.com", "freshersworld.com", "ambitionbox.com"
]

LOCATION_KEYWORDS = ["hyderabad", "secunderabad"]
ENTRY_KEYWORDS = [
    "fresher", "freshers", "entry level", "entry-level", "0-1", "0-2",
    "0–1", "0–2", "junior", "trainee", "graduate", "associate", "intern",
    "early career", "0 to 1", "0 to 2", "less than 2 years"
]
SENIOR_KEYWORDS = [
    "3+ years", "4+ years", "5+ years", "6+ years", "7+ years", "8+ years",
    "3 years experience", "4 years experience", "5 years experience",
    "6 years experience", "7 years experience", "8 years experience",
    "senior manager", "principal engineer", "architect", "tech lead", "technical lead"
]
ARTICLE_ONLY_KEYWORDS = [
    "salary in india", "salary guide", "salary trends", "average salary",
    "salary insights", "how to become", "career roadmap", "roadmap to",
    "tutorial", "course", "training", "certification", "learn java",
    "java tools", "interview questions", "interview preparation", "what is java",
    "skills in demand", "digital skills in demand", "career in java"
]


def search_web(query):
    encoded = urllib.parse.quote(query)
    url = "https://html.duckduckgo.com/html/?q=" + encoded
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
            "Accept-Language": "en-IN,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="ignore")


def clean_text(text):
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_id(title, link):
    return hashlib.sha256(f"{title}|{link}".lower().encode()).hexdigest()[:16]


def load_existing():
    existing = set()
    if not CSV_FILE.exists():
        return existing
    with open(CSV_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            link = row.get("Apply Link", "").strip()
            title = row.get("Job Title", "").strip()
            if link:
                existing.add(link)
            elif title:
                existing.add(make_id(title, ""))
    return existing


def normalize_result_url(href):
    href = unescape(href or "")
    match = re.search(r"uddg=([^&]+)", href)
    if match:
        return urllib.parse.unquote(match.group(1))
    return href


def parse_search_results(html):
    results = []
    # DuckDuckGo result blocks contain a result link and a short snippet.
    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<div class="result|$)',
        re.I | re.S,
    )
    for match in pattern.finditer(html):
        link = normalize_result_url(match.group(1))
        title = clean_text(match.group(2))
        block = match.group(3)
        snippet_match = re.search(r'class="result__snippet"[^>]*>(.*?)</', block, re.I | re.S)
        snippet = clean_text(snippet_match.group(1)) if snippet_match else clean_text(block)
        if link.startswith("http") and title:
            results.append({"title": title, "link": link, "description": snippet})
    return results


def looks_like_job(title, description, link):
    text = f"{title} {description} {link}".lower()

    if "java" not in text:
        return False
    if not any(k in text for k in LOCATION_KEYWORDS):
        return False
    if any(k in text for k in ARTICLE_ONLY_KEYWORDS):
        return False

    # Prefer known job boards and reject obvious non-job domains/pages.
    known_site = any(site in text for site in JOB_SITES)
    job_signal = any(k in text for k in [
        "job", "jobs", "hiring", "opening", "openings", "vacancy", "apply",
        "recruitment", "job description", "responsibilities", "qualifications",
        "career", "position", "role"
    ])
    if not (known_site or job_signal):
        return False

    return True


def score_job(title, description, link):
    text = f"{title} {description} {link}".lower()
    score = 0
    if "java" in text:
        score += 30
    if "full stack" in text:
        score += 25
    if "spring boot" in text:
        score += 20
    if "microservices" in text:
        score += 10
    if "rest api" in text or "restful" in text:
        score += 7
    if "react" in text or "angular" in text:
        score += 8
    if "sql" in text or "mysql" in text or "oracle" in text:
        score += 5
    if "hibernate" in text or "jpa" in text:
        score += 5
    if any(k in text for k in LOCATION_KEYWORDS):
        score += 25
    if any(k in text for k in ENTRY_KEYWORDS):
        score += 25
    if any(k in text for k in SENIOR_KEYWORDS):
        score -= 50
    if any(site in text for site in JOB_SITES):
        score += 15
    return score


def parse_results(html):
    jobs = []
    for result in parse_search_results(html):
        title = result["title"]
        link = result["link"]
        description = result["description"]
        if not looks_like_job(title, description, link):
            continue
        score = score_job(title, description, link)
        if score < 50:
            continue
        jobs.append({
            "title": title,
            "link": link,
            "description": description,
            "score": score,
        })
    return jobs


def append_jobs(jobs):
    CSV_FILE.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "Date Found", "Job Title", "Company", "Location", "Experience",
        "Salary", "Posted", "Source", "Apply Link"
    ]
    file_exists = CSV_FILE.exists() and CSV_FILE.stat().st_size > 0
    existing = load_existing()
    added = 0

    with open(CSV_FILE, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not file_exists:
            writer.writeheader()

        for job in jobs:
            if job["link"] in existing:
                continue
            source = urllib.parse.urlparse(job["link"]).netloc.replace("www.", "")
            writer.writerow({
                "Date Found": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "Job Title": job["title"],
                "Company": "See job posting",
                "Location": "Hyderabad, India",
                "Experience": "Verify in posting",
                "Salary": "Not disclosed",
                "Posted": "Verify in posting",
                "Source": source,
                "Apply Link": job["link"],
            })
            existing.add(job["link"])
            added += 1
    return added


def main():
    all_jobs = []
    print("Searching public web job listings for Hyderabad Java roles...")

    for query in SEARCHES:
        print(f"Searching: {query}")
        try:
            html = search_web(query)
            jobs = parse_results(html)
            print(f"  Job postings accepted: {len(jobs)}")
            all_jobs.extend(jobs)
        except Exception as e:
            print(f"Search failed for '{query}': {e}")

    unique = {}
    for job in all_jobs:
        key = job["link"]
        if key not in unique or job["score"] > unique[key]["score"]:
            unique[key] = job

    jobs = sorted(unique.values(), key=lambda x: x["score"], reverse=True)[:20]
    added = append_jobs(jobs)
    print(f"Found {len(jobs)} actual job-posting candidates.")
    print(f"Added {added} new jobs to the tracker.")


if __name__ == "__main__":
    main()
