# crawl_from_google_dork_results_filtered.py
# 依赖：pip install requests beautifulsoup4 lxml
# 可选（JS站点更稳）：pip install playwright && playwright install
# 可选（PDF抽文本）：pip install pypdf
# 可选（DOCX抽文本）：pip install python-docx

import os, re, json, time, hashlib
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

def main():
    # ========= 配置区（不需要终端输入） =========
    GOOGLE_DORK_RESULTS_DIR = "google_dork_results"
    OUTPUT_DIR = "crawl_corpus"
    SKIP_FILENAMES = {"summary_report.txt"}

    MAX_FOLLOW_FROM_DIRECTORY = 3
    TIMEOUT_SEC = 20
    SLEEP_SEC = 0.25
    USE_PLAYWRIGHT_FALLBACK = True

    # 只输出“正文内容”的标准（你可以调严）
    MIN_ARTICLE_TEXT_LEN = 350          # 正文字符数阈值
    # =======================================

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 全量日志（包含目录/失败）
    JSONL_ALL = os.path.join(OUTPUT_DIR, "extracted_all.jsonl")

    # 只保留正文（最终用于后续处理）
    JSONL_ART = os.path.join(OUTPUT_DIR, "articles.jsonl")
    TXT_ART_DIR = os.path.join(OUTPUT_DIR, "articles_txt")
    os.makedirs(TXT_ART_DIR, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"})

    pw = browser = context = None
    if USE_PLAYWRIGHT_FALLBACK:
        try:
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(user_agent=session.headers["User-Agent"])
        except Exception:
            pw = browser = context = None

    def sha16(s: str) -> str:
        return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()[:16]

    def normalize_url(u: str) -> str:
        u = (u or "").strip()
        u = u.split("#", 1)[0]
        return u

    def safe_name(s: str) -> str:
        s = re.sub(r"[^\w\-.]+", "_", s, flags=re.UNICODE).strip("_")
        return (s[:180] if s else "untitled")

    def looks_like_binary_by_ext(u: str) -> bool:
        p = urlparse(u).path.lower()
        ext = p.rsplit(".", 1)[-1] if "." in p else ""
        return ext in {"pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "zip", "rar", "7z", "mp3", "mp4"}

    def fetch(url: str):
        url = normalize_url(url)
        # requests first
        try:
            r = session.get(url, timeout=TIMEOUT_SEC, allow_redirects=True)
            ct = (r.headers.get("content-type") or "").lower()
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}")
            if ("application/pdf" in ct) or url.lower().endswith(".pdf"):
                return {"ok": True, "final_url": r.url, "status": r.status_code, "ct": ct or "application/pdf", "body": r.content, "via": "requests-binary"}
            if ("text/html" in ct) or ("<html" in (r.text or "").lower()):
                return {"ok": True, "final_url": r.url, "status": r.status_code, "ct": ct or "text/html", "body": r.text, "via": "requests"}
            if isinstance(r.text, str) and r.text.strip():
                return {"ok": True, "final_url": r.url, "status": r.status_code, "ct": ct or "text/plain", "body": r.text, "via": "requests"}
        except Exception:
            pass

        # playwright fallback
        if context is None:
            return {"ok": False, "final_url": url, "status": None, "ct": "", "body": "", "via": "none"}

        try:
            page = context.new_page()
            def route_handler(route):
                rt = route.request.resource_type
                if rt in ("image", "media", "font"):
                    route.abort()
                else:
                    route.continue_()
            page.route("**/*", route_handler)
            page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_SEC * 1000)
            time.sleep(0.6)
            html = page.content()
            final_url = page.url
            page.close()
            return {"ok": True, "final_url": final_url, "status": 200, "ct": "text/html", "body": html, "via": "playwright"}
        except Exception:
            try:
                page.close()
            except Exception:
                pass
            return {"ok": False, "final_url": url, "status": None, "ct": "text/html", "body": "", "via": "playwright-fail"}

    def extract_pdf_text(pdf_bytes: bytes) -> str:
        try:
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(pdf_bytes))
            parts = []
            for pg in reader.pages:
                t = pg.extract_text() or ""
                t = re.sub(r"[ \t]+\n", "\n", t)
                parts.append(t.strip())
            return "\n\n".join([p for p in parts if p]).strip()
        except Exception:
            return ""

    def extract_docx_text(docx_bytes: bytes) -> str:
        try:
            import io
            from docx import Document
            doc = Document(io.BytesIO(docx_bytes))
            ps = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
            return "\n".join(ps).strip()
        except Exception:
            return ""

    def extract_main_html(html: str, base_url: str):
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript", "svg", "canvas", "iframe", "form", "nav", "footer", "header", "aside"]):
            tag.decompose()

        title = ""
        h1 = soup.find("h1")
        if h1 and h1.get_text(" ", strip=True):
            title = h1.get_text(" ", strip=True)
        elif soup.title and soup.title.get_text(strip=True):
            title = soup.title.get_text(strip=True)

        date = ""
        for meta_sel in [
            ("meta", {"property": "article:published_time"}),
            ("meta", {"name": "pubdate"}),
            ("meta", {"name": "publishdate"}),
            ("meta", {"name": "date"}),
            ("meta", {"name": "DC.date"}),
            ("meta", {"name": "DC.Date"}),
            ("meta", {"name": "DCTERMS.issued"}),
        ]:
            m = soup.find(meta_sel[0], meta_sel[1])
            if m and m.get("content"):
                date = m.get("content").strip()
                break
        if not date:
            t = soup.find("time")
            if t and (t.get("datetime") or t.get_text(" ", strip=True)):
                date = (t.get("datetime") or t.get_text(" ", strip=True)).strip()
        if not date:
            m = re.search(r"(\b20\d{2}[-/\.]\d{1,2}[-/\.]\d{1,2}\b|\b\d{1,2}\s+[A-Za-z]{3,9}\s+20\d{2}\b|\b[A-Za-z]{3,9}\.?\s+\d{1,2},\s*20\d{2}\b)",
                          soup.get_text(" ", strip=True))
            if m:
                date = m.group(1)

        best = None
        best_score = -10**18
        candidates = soup.select("article, main, div#content, div.content, div.article, div.post, section.content, section.article")
        if not candidates:
            candidates = soup.find_all(["div", "section", "main", "article"])
        for node in candidates:
            txt = node.get_text(" ", strip=True)
            if len(txt) < 200:
                continue
            link_txt = " ".join(a.get_text(" ", strip=True) for a in node.find_all("a"))
            score = len(txt) - 2 * len(link_txt)
            if score > best_score:
                best_score = score
                best = node
        if best is None:
            best = soup.body or soup

        raw = best.get_text("\n", strip=True)
        raw = re.sub(r"\n{3,}", "\n\n", raw).strip()

        total_len = len(best.get_text(" ", strip=True))
        link_len = len(" ".join(a.get_text(" ", strip=True) for a in best.find_all("a")))
        link_density = (link_len / total_len) if total_len else 1.0

        lines = []
        for ln in raw.splitlines():
            ln = ln.strip()
            if not ln or len(ln) <= 2:
                continue
            if re.fullmatch(r"(home|news|back|next|previous|menu|search|share|print|download|archive|category|tags?)", ln, flags=re.I):
                continue
            lines.append(ln)
        text = "\n".join(lines).strip()

        page_links = []
        for a in soup.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            if not href or href.startswith(("mailto:", "javascript:", "tel:")):
                continue
            full = normalize_url(urljoin(base_url, href))
            if full:
                page_links.append(full)

        seen = set()
        uniq = []
        for u in page_links:
            if u not in seen:
                seen.add(u)
                uniq.append(u)

        return {"title": title, "date": date, "text": text, "link_density": link_density, "page_links": uniq}

    def is_directory_like(extracted: dict) -> bool:
        text = (extracted.get("text") or "").strip()
        ld = extracted.get("link_density", 1.0)
        links = extracted.get("page_links") or []
        if len(text) < 300 and (len(links) > 60 or ld > 0.35):
            return True
        if len(text) < 180 and len(links) > 20:
            return True
        if re.search(r"(page\s*\d+|pagination|next|previous|older|newer|archives?)", text, flags=re.I) and len(links) > 50:
            return True
        return False

    def pick_article_links(seed_url: str, page_links: list):
        seed = urlparse(seed_url)
        host = seed.netloc.lower()
        scored = []
        for u in page_links:
            pu = urlparse(u)
            if not pu.scheme.startswith("http"):
                continue
            if pu.netloc.lower() != host:
                continue
            if normalize_url(u) == normalize_url(seed_url):
                continue
            path = pu.path.lower()
            if any(path.endswith("." + ext) for ext in ["jpg","jpeg","png","gif","webp","svg","mp4","mp3","zip","rar","7z"]):
                continue
            s = 0
            if re.search(r"/(news|press|siaran-pers|transkrip|speech|speeches|view|post|article|berita|detail|statement|release)/", path):
                s += 5
            if re.search(r"/\d{4}/\d{1,2}/\d{1,2}/", path):
                s += 4
            if re.search(r"\d{4,}", path):
                s += 2
            if len(path.strip("/").split("/")) >= 3:
                s += 1
            if "page=" in (pu.query or "").lower():
                s -= 3
            if re.search(r"/(category|categories|tag|search|index|list|lists|archive|page)/", path):
                s -= 4
            if s > 0:
                scored.append((s, normalize_url(u)))
        scored.sort(key=lambda x: x[0], reverse=True)
        picked = []
        for _, u in scored:
            if u not in picked:
                picked.append(u)
            if len(picked) >= MAX_FOLLOW_FROM_DIRECTORY:
                break
        return picked

    # 1) 自动找 txt（排除 summary_report.txt）
    txt_files = []
    for root, _, files in os.walk(GOOGLE_DORK_RESULTS_DIR):
        for fn in files:
            if not fn.lower().endswith(".txt"):
                continue
            if fn in SKIP_FILENAMES:
                continue
            txt_files.append(os.path.join(root, fn))

    # 2) 从 txt 抽 URL
    all_urls = []
    seen_url = set()
    for fp in sorted(txt_files):
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                for ln, line in enumerate(f, 1):
                    s = line.strip()
                    u = ""
                    if s.startswith("URL:"):
                        u = s.split("URL:", 1)[1].strip()
                    elif re.match(r"^https?://", s):
                        u = s
                    if u:
                        u = normalize_url(u)
                        if u and u not in seen_url:
                            seen_url.add(u)
                            all_urls.append({"seed_url": u, "src_file": os.path.basename(fp), "src_line": ln})
        except Exception:
            continue

    # 3) 抓取：全量写 JSONL_ALL；只有“正文合格”的才写 JSONL_ART + articles_txt
    visited = set()
    with open(JSONL_ALL, "w", encoding="utf-8") as wf_all, open(JSONL_ART, "w", encoding="utf-8") as wf_art:
        def write_all(rec: dict):
            wf_all.write(json.dumps(rec, ensure_ascii=False) + "\n")
            wf_all.flush()

        def write_article(rec: dict):
            # 只收正文：非目录 + text 达标
            text = (rec.get("text") or "").strip()
            if rec.get("is_directory") is True:
                return
            if len(text) < MIN_ARTICLE_TEXT_LEN:
                return
            # 写 articles.jsonl
            wf_art.write(json.dumps(rec, ensure_ascii=False) + "\n")
            wf_art.flush()
            # 写 articles_txt/*.txt
            fn = safe_name(f"{rec.get('src_file','')}_{sha16(rec.get('final_url',''))}_{(rec.get('title') or 'no_title')[:80]}") + ".txt"
            with open(os.path.join(TXT_ART_DIR, fn), "w", encoding="utf-8", errors="ignore") as tf:
                tf.write(
                    f"seed_url: {rec.get('seed_url','')}\n"
                    f"final_url: {rec.get('final_url','')}\n"
                    f"title: {rec.get('title','')}\n"
                    f"date: {rec.get('date','')}\n"
                    f"via: {rec.get('via','')}\n"
                    f"http_status: {rec.get('http_status','')}\n"
                    f"content_type: {rec.get('content_type','')}\n"
                    f"note: {rec.get('note','')}\n\n"
                )
                tf.write(text)

        for item in all_urls:
            seed_url = item["seed_url"]
            if seed_url in visited:
                continue
            visited.add(seed_url)

            base_rec = {
                "src_file": item["src_file"],
                "src_line": item["src_line"],
                "seed_url": seed_url,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            # 二进制
            if looks_like_binary_by_ext(seed_url):
                got = fetch(seed_url)
                rec = dict(base_rec)
                rec.update({
                    "final_url": got.get("final_url", seed_url),
                    "via": got.get("via", ""),
                    "http_status": got.get("status", None),
                    "content_type": got.get("ct", ""),
                    "is_directory": False,
                    "followed_from_directory": False,
                    "title": "",
                    "date": "",
                    "text": "",
                    "note": ""
                })
                if got.get("ok") and isinstance(got.get("body"), (bytes, bytearray)):
                    ct = (rec["content_type"] or "").lower()
                    path = urlparse(rec["final_url"]).path.lower()
                    if ("pdf" in ct) or path.endswith(".pdf"):
                        rec["text"] = extract_pdf_text(got["body"])
                        rec["title"] = os.path.basename(urlparse(rec["final_url"]).path) or "PDF"
                        rec["note"] = "pdf_extracted" if rec["text"] else "pdf_no_text"
                    elif path.endswith(".docx"):
                        rec["text"] = extract_docx_text(got["body"])
                        rec["title"] = os.path.basename(urlparse(rec["final_url"]).path) or "DOCX"
                        rec["note"] = "docx_extracted" if rec["text"] else "docx_no_text"
                    else:
                        rec["note"] = "binary_unsupported"
                else:
                    rec["note"] = "binary_fetch_failed"

                write_all(rec)
                write_article(rec)  # 如果抽到的文本达标，会进入 articles 输出
                time.sleep(SLEEP_SEC)
                continue

            got = fetch(seed_url)
            if not got.get("ok") or not got.get("body"):
                rec = dict(base_rec)
                rec.update({
                    "final_url": got.get("final_url", seed_url),
                    "via": got.get("via", ""),
                    "http_status": got.get("status", None),
                    "content_type": got.get("ct", ""),
                    "is_directory": False,
                    "followed_from_directory": False,
                    "title": "",
                    "date": "",
                    "text": "",
                    "note": "fetch_failed"
                })
                write_all(rec)
                time.sleep(SLEEP_SEC)
                continue

            extracted = extract_main_html(got["body"], got.get("final_url", seed_url))
            dir_like = is_directory_like(extracted)

            # 先尝试把 seed 当作正文页处理
            rec_seed = dict(base_rec)
            rec_seed.update({
                "final_url": got.get("final_url", seed_url),
                "via": got.get("via", ""),
                "http_status": got.get("status", None),
                "content_type": got.get("ct", ""),
                "is_directory": bool(dir_like),
                "followed_from_directory": False,
                "title": extracted.get("title", ""),
                "date": extracted.get("date", ""),
                "text": extracted.get("text", "") if not dir_like else "",
                "note": "ok" if not dir_like else "directory"
            })
            write_all(rec_seed)
            write_article(rec_seed)

            # 如果是目录页：跟进抓正文
            if dir_like:
                follow_links = pick_article_links(got.get("final_url", seed_url), extracted.get("page_links", []))
                # 更新 seed 的跟进信息（全量日志用）
                rec_seed["followed_from_directory"] = bool(follow_links)
                rec_seed["note"] = f"directory_following_{len(follow_links)}" if follow_links else "directory_no_follow_links"
                # 重新写一条 seed 的最终状态（可选：你想要一条就删除下面两行）
                # write_all(rec_seed)

                for fu in follow_links:
                    if fu in visited:
                        continue
                    visited.add(fu)

                    g2 = fetch(fu)
                    if not g2.get("ok") or not g2.get("body"):
                        rec = dict(base_rec)
                        rec.update({
                            "seed_url": seed_url,
                            "final_url": g2.get("final_url", fu),
                            "via": g2.get("via", ""),
                            "http_status": g2.get("status", None),
                            "content_type": g2.get("ct", ""),
                            "is_directory": False,
                            "followed_from_directory": True,
                            "title": "",
                            "date": "",
                            "text": "",
                            "note": "follow_fetch_failed"
                        })
                        write_all(rec)
                        time.sleep(SLEEP_SEC)
                        continue

                    ex2 = extract_main_html(g2["body"], g2.get("final_url", fu))
                    rec = dict(base_rec)
                    rec.update({
                        "seed_url": seed_url,
                        "final_url": g2.get("final_url", fu),
                        "via": g2.get("via", ""),
                        "http_status": g2.get("status", None),
                        "content_type": g2.get("ct", ""),
                        "is_directory": is_directory_like(ex2),
                        "followed_from_directory": True,
                        "title": ex2.get("title", ""),
                        "date": ex2.get("date", ""),
                        "text": ex2.get("text", ""),
                        "note": "follow_ok"
                    })
                    write_all(rec)
                    write_article(rec)
                    time.sleep(SLEEP_SEC)

            time.sleep(SLEEP_SEC)

    if context is not None:
        try: context.close()
        except Exception: pass
    if browser is not None:
        try: browser.close()
        except Exception: pass
    if pw is not None:
        try: pw.stop()
        except Exception: pass

if __name__ == "__main__":
    main()
