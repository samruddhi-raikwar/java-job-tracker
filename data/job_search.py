import csv
import hashlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

CSV_FILE = Path("data/job_tracker.csv")

SEARCHES = [
    '"Java Full Stack Developer" Hyderabad fresher',
    '"Java Full Stack Developer" Hyderabad "0-2 years"',
    '"Java Developer" Hyderabad fresher Spring Boot',
    '"Java Full Stack" Hyderabad "entry level"',
    '"Spring Boot" Java developer Hyderabad fresher',
]

GOOD_KEYWORDS = [
    "java",
    "spring boot",
    "spring",
    "full stack",
    "microservices",
    "rest api",
    "react",
    "angular",
    "sql",
    "hibernate",
]

LOCATION_KEYWORDS = [
    "hyderabad",
    "secunderabad",
]

ENTRY_KEYWORDS = [
    "fresher",
    "freshers",
    "entry level",
    "0-1",
    "0-2",
    "0–1",
    "0–2",
    "junior",
    "trainee",
    "graduate",
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
    return re.sub(r"\s+", " ", text or "").strip()


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

    # Java / full stack relevance
    if "java" in text:
        score += 25

    if "full stack" in text:
        score += 25

    if "spring boot" in text:
        score += 15

    if "microservices" in text:
        score += 10

    if "react" in text or "angular" in text:
        score += 8

    if "sql" in text:
        score += 5

    # Hyderabad
    if "hyderabad" in text or "secunderabad" in text:
        score += 15

    # Fresher suitability
    for keyword in ENTRY_KEYWORDS:
        if keyword in text:
            score += 10
            break

    # Penalize clearly senior jobs
    senior_keywords = [
        "5+ years",
        "6+ years",
        "7+ years",
        "8+ years",
        "10+ years",
        "senior manager",
        "principal engineer",
        "architect",
        "tech lead",
    ]

    for keyword in senior_keywords:
        if keyword in text:
            score -= 30

    return score


def parse_feed(xml_data):
    root = ET.fromstring(xml_data)

    jobs = []

    for item in root.findall(".//item"):
        title = clean_text(
            item.findtext("title", "")
        )

        link = clean_text(
            item.findtext("link", "")
        )

        description = clean_text(
            item.findtext("description", "")
        )

        published = clean_text(
            item.findtext("pubDate", "")
        )

        if not title or not link:
            continue

        score = score_job(title, description)

        # Require basic relevance
        text = f"{title} {description}".lower()

        if "java" not in text:
            continue

        if not any(
            keyword in text
            for keyword in LOCATION_KEYWORDS
        ):
            continue

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
        "Date Found",
        "Job Title",
        "Company",
        "Location",
        "Experience",
        "Salary",
        "Posted",
        "Source",
        "Apply Link",
    ]

    existing = load_existing()

    added = 0

    with open(
        CSV_FILE,
        "a",
        encoding="utf-8",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fields
        )

        if not file_exists or CSV_FILE.stat().st_size == 0:
            writer.writeheader()

        for job in jobs:

            if job["link"] in existing:
                continue

            title = job["title"]

            # Try to identify company/source from title
            company = "See job posting"

            source = urllib.parse.urlparse(
                job["link"]
            ).netloc

            writer.writerow({
                "Date Found": datetime.now(
                    timezone.utc
                ).strftime("%Y-%m-%d"),

                "Job Title": title,

                "Company": company,

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

            all_jobs.extend(jobs)

        except Exception as e:
            print(
                f"Search failed for '{query}': {e}"
            )

    # Remove duplicates
    unique = {}

    for job in all_jobs:

        key = job["link"]

        if key not in unique:
            unique[key] = job

    jobs = list(unique.values())

    # Best matches first
    jobs.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    # Add only the best 10 new results per run
    jobs = jobs[:10]

    added = append_jobs(jobs)

    print(
        f"Found {len(jobs)} relevant results."
    )

    print(
        f"Added {added} new jobs to the tracker."
    )


if __name__ == "__main__":
    main()
