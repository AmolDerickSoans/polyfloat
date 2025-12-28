import os
import time
from urllib.parse import urljoin, urldefrag, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://docs.polymarket.com/polymarket-learn/"
OUT_DIR = "docs/polymarket-learn-docs"
DELAY_SECONDS = 0  # be nice

session = requests.Session()
session.headers.update(
    {"User-Agent": "polymarket-docs-scraper/1.0 (+https://example.com)"}
)


def normalize_url(url: str) -> str:
    # Remove fragments, keep only https://docs.polymarket.com/*
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    if not parsed.netloc:
        # relative -> absolute
        url = urljoin(BASE_URL, url)
        parsed = urlparse(url)
    if parsed.netloc != urlparse(BASE_URL).netloc:
        return ""  # external link
    # Force trailing slash behavior normalization
    if not parsed.path:
        path = "/"
    else:
        path = parsed.path
    return parsed._replace(path=path).geturl()


def save_page(url: str, html: str):
    parsed = urlparse(url)
    path = parsed.path

    soup = BeautifulSoup(html, "html.parser")
    # Extract main content
    content = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_="md-content")
        or soup.body
    )
    if content:
        text = content.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)

    if path.endswith("/"):
        file_path = os.path.join(OUT_DIR, path.lstrip("/"), "index.txt")
    else:
        # e.g. /foo/bar -> /foo/bar.txt
        file_path = os.path.join(OUT_DIR, path.lstrip("/") + ".txt")

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Saved {url} -> {file_path}")


def extract_links(html: str, base_url: str) -> set:
    soup = BeautifulSoup(html, "html.parser")
    links = set()

    # All <a> tags
    for a in soup.find_all("a", href=True):
        href = a["href"]
        norm = normalize_url(urljoin(base_url, href))
        if norm:
            links.add(norm)

    return links


def crawl(start_url: str):
    to_visit = {normalize_url(start_url)}
    visited = set()

    while to_visit:
        url = to_visit.pop()
        if not url or url in visited:
            continue

        print(f"Crawling: {url}")
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code != 200:
                print(f"Non-200 for {url}: {resp.status_code}")
                visited.add(url)
                continue
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            visited.add(url)
            continue

        html = resp.text
        save_page(url, html)

        # Discover new links
        new_links = extract_links(html, url)
        for link in new_links:
            if link.startswith(BASE_URL) and link not in visited:
                to_visit.add(link)

        visited.add(url)
        time.sleep(DELAY_SECONDS)


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    crawl(BASE_URL)
