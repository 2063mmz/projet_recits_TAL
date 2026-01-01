from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time
import os
import re

BASE_DOMAIN = "https://eng.yidaiyilu.gov.cn"
LIST_URL = "https://eng.yidaiyilu.gov.cn/list/c/insights?page={}"
OUTPUT_DIR = "bri_insights_txt"

# 页面日期长这样：Dec.19, 2025
DATE_RE = re.compile(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.\s*\d{1,2},\s*\d{4}\b')

def clean_filename(text: str) -> str:
    text = re.sub(r'[\\/*?:"<>|]', '', text)
    return text[:120].strip()

def ensure_dir(path: str):
    if not os.path.exists(path):
        os.makedirs(path)

def to_full_url(href: str) -> str | None:
    if not href:
        return None
    if href.startswith("/"):
        return BASE_DOMAIN + href
    if href.startswith("http"):
        return href
    return None

def extract_insight_links(html: str):
    """
    严格按 /list/c/insights 的结构抽取文章：
    - 只取包含日期的 li（列表项）
    - 只取 href 像 /p/<id>.html 的链接（文章详情页）
    """
    soup = BeautifulSoup(html, "html.parser")
    links = []
    seen = set()

    for li in soup.find_all("li"):
        li_text = li.get_text(" ", strip=True)
        if not DATE_RE.search(li_text):
            continue

        a = li.find("a", href=True)
        if not a:
            continue

        href = a["href"].strip()
        url = to_full_url(href)
        if not url:
            continue

        # 文章详情页特征：/p/... .html
        url_l = url.lower()
        if "/p/" not in url_l or not url_l.endswith(".html"):
            continue

        title = a.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        if url in seen:
            continue
        seen.add(url)

        links.append({"title": title, "url": url})

    return links

def parse_article(html: str):
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    for tag in ["h1", "h2", "title"]:
        t = soup.find(tag)
        if t:
            title = t.get_text(strip=True)
            if len(title) > 5:
                break

    for tag in soup(["script", "style", "nav", "footer", "header", "iframe"]):
        tag.decompose()

    main = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", class_=re.compile("content|article|main", re.I))
        or soup.body
    )

    paras = main.find_all(["p", "h2", "h3"]) if main else []
    content = []
    seen = set()

    for p in paras:
        text = p.get_text(strip=True)
        if len(text) < 30:
            continue
        if text in seen:
            continue
        seen.add(text)
        content.append(text)

    return title, "\n\n".join(content)

def main():
    ensure_dir(OUTPUT_DIR)

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=False)  # 不想显示窗口就改 True
        page = browser.new_page()
        page.route("**/*", lambda route: route.abort()
           if route.request.resource_type in ["media", "image", "font"]
           else route.continue_())

        saved = 0

        for page_num in range(1, 5):
            url = LIST_URL.format(page_num)
            print(f"Page {page_num}: {url}")

            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            time.sleep(1)

            links = extract_insight_links(page.content())
            print(f"  Found {len(links)} articles")

            for item in links:
                try:
                    page.goto(item["url"], wait_until="domcontentloaded", timeout=90000)
                    page.wait_for_selector("body", timeout=30000)
                    time.sleep(0.5)

                    title, content = parse_article(page.content())
                    if not content:
                        continue

                    fname = clean_filename(title) or f"article_{saved}"
                    path = os.path.join(OUTPUT_DIR, fname + ".txt")

                    with open(path, "w", encoding="utf-8") as f:
                        f.write(title + "\n\n")
                        f.write("=" * 80 + "\n\n")
                        f.write(content)

                    saved += 1
                except Exception as e:
                    print("  Failed:", item["url"], e)

        browser.close()

    print(f"Done. Saved {saved} BRI Insights articles.")

if __name__ == "__main__":
    main()
