import csv
import hashlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

CSV_FILE = Path("data/job_tracker.csv")

# Google News RSS is used because it can be queried without paid job-board APIs.
# Keep the searches broad enough that relevant listings are not lost because
# "Hyderabad" or "fresher" is missing from the article snippet.
SEARCHES = [
    'Java Developer Hyderabad fresher',
    'Java Developer Hyderabad "0-2 years"',
    'Java Full Stack Developer Hyderabad',
    'Java Spring Boot Developer Hyderabad fresher',
    'Java Full Stack Hyderabad entry level',
    'Junior Java Developer Hyderabad',
    'Trainee Java Developer Hyderabad',
    'Java Developer Hyderabad graduate',
]

LOCATION_KEYWORDS = ["hyderabad", "secunderabad"]

ENTRY_KEYWORDS = [
    "fresher", "freshers", "entry level", "entry-level", "0-1", "0-2",
    "0–1", "0–2", "junior", "trainee", "graduate", "associate",
    "intern", "early career"
]

SENIOR_KEYWORDS = [
    "5+ years", "6+ years", "7+ years", "8+ years", "10+ years",
    "5 years experience", "6 years experience", "7 years experience",
    "8 years experience", "10 years experience", "senior manager",
    "principal engineer", "architect", "tech lead", "technical lead"
]


def google_news_rss(query):
    encoded = urllib.parse.quote(query)
    url = (
        "https://news.google.com/rss/search?"
        f"q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
    )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def clean_text(text):
    # Remove simple HTML tags/entities from Google News descriptions.
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_id(title, link):
    value = f"{title}|{link}".lower()
    return hashlib.sha256(value.encode()).hexdigest()[:16]


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


def score_job(title, description):
    text = f"{title} {description}".lower()
    score = 0

    if "java" in text:
        score += 30
    if "full stack" in text:
        score += 25
    if "spring boot" in text:
        score += 20
    if "spring" in text:
        score += 5
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
        score += 20

    if any(k in text for k in ENTRY_KEYWORDS):
        score += 20

    if any(k in text for k in SENIOR_KEYWORDS):
        score -= 35

    return score


def parse_feed(xml_data):
    root = ET.fromstring(xml_data)
    jobs = []

    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title", ""))
        link = clean_text(item.findtext("link", ""))
        description = clean_text(item.findtext("description", ""))
        published = clean_text(item.findtext("pubDate", ""))

        if not title or not link:
            continue

        text = f"{title} {description}".lower()

        # The query already contains Hyderabad. Do NOT require the word
        # Hyderabad to appear again in the RSS snippet; many job listings
        # omit the location from their title/description.
        if "java" not in text:
            continue

        score = score_job(title, description)

        jobs.append({
            "title": title,
            "link": link,
            "description": description,
            "published": published,
            "score": score,
        })

    return jobs


def append_jobs(jobs):
    CSV_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_exists = CSV_FILE.exists()

    fields = [
        "Date Found", "Job Title", "Company", "Location", "Experience",
        "Salary", "Posted", "Source", "Apply Link"
    ]

    existing = load_existing()
    added = 0

    with open(CSV_FILE, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)

        if not file_exists or CSV_FILE.stat().st_size == 0:
            writer.writeheader()

        for job in jobs:
            if job["link"] in existing:
                continue

            source = urllib.parse.urlparse(job["link"]).netloc

            writer.writerow({
                "Date Found": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "Job Title": job["title"],
                "Company": "See job posting",
                "Location": "Hyderabad, India",
                "Experience": "Verify in posting",
                "Salary": "Not disclosed",
                "Posted": job["published"],
                "Source": source,
                "Apply Link": job["link"],
            })

            existing.add(job["link"])
            added += 1

    return added


def main():
    all_jobs = []
    print("Searching for new Hyderabad Java jobs...")

    for query in SEARCHES:
        print(f"Searching: {query}")
        try:
            data = google_news_rss(query)
            jobs = parse_feed(data)
            print(f"  RSS results accepted: {len(jobs)}")
            all_jobs.extend(jobs)
        except Exception as e:
            print(f"Search failed for '{query}': {e}")

    unique = {}
    for job in all_jobs:
        key = job["link"]
        if key not in unique or job["score"] > unique[key]["score"]:
            unique[key] = job

    jobs = list(unique.values())
    jobs.sort(key=lambda x: x["score"], reverse=True)

    # Keep only useful matches and avoid filling the tracker with weak results.
    jobs = [job for job in jobs if job["score"] >= 30][:15]

    added = append_jobs(jobs)

    print(f"Found {len(jobs)} relevant results.")
    print(f"Added {added} new jobs to the tracker.")


if __name__ == "__main__":
    main()
