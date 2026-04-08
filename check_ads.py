"""
Podarimo.si - Monitor novih oglasov
Shranjuje stanje via GitHub API (brez git push problemov)
"""

import base64
import json
import os
import re
import time

import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
GITHUB_TOKEN     = os.environ["GITHUB_TOKEN"]
GITHUB_REPO      = os.environ["GITHUB_REPOSITORY"]  # samodejno: "user/repo"

BASE_URL = "https://www.podarimo.si"
SEEN_FILE_PATH = "seen_ads.json"

PAGES = [
    f"{BASE_URL}/podarim/vsi-oglasi/stran-1",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36"
}

GH_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}


# ── GitHub API za shranjevanje seen_ads.json ──────────────────────────────────

def load_seen():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{SEEN_FILE_PATH}"
    resp = requests.get(url, headers=GH_HEADERS, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return set(json.loads(content)), data["sha"]
    return set(), None


def save_seen(seen, sha):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{SEEN_FILE_PATH}"
    content = base64.b64encode(
        json.dumps(sorted(list(seen)), ensure_ascii=False).encode("utf-8")
    ).decode("utf-8")
    body = {"message": "update seen ads", "content": content}
    if sha:
        body["sha"] = sha
    resp = requests.put(url, headers=GH_HEADERS, json=body, timeout=10)
    if resp.ok:
        print(f"[*] seen_ads.json shranjen ({len(seen)} oglasov)")
    else:
        print(f"[!] Napaka pri shranjevanju: {resp.text}")


# ── Scraping ──────────────────────────────────────────────────────────────────

def fetch_ads(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
    except Exception as e:
        print(f"[!] Napaka: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    ads = []
    seen_ids = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        match = re.search(r"/(\d{5,})-([^/\s]+)$", href)
        if not match:
            continue
        ad_id = match.group(1)
        slug  = match.group(2)
        title = a.get("title") or a.get_text(strip=True) or slug.replace("-", " ")
        if title and len(title) > 2 and ad_id not in seen_ids:
            seen_ids.add(ad_id)
            full_url = href if href.startswith("http") else BASE_URL + href
            ads.append({"id": ad_id, "title": title, "url": full_url})

    return ads


# ── Telegram ──────────────────────────────────────────────────────────────────

def send_telegram(message):
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message,
                  "parse_mode": "HTML", "disable_web_page_preview": False},
            timeout=10,
        )
        if not resp.ok:
            print(f"[!] Telegram napaka: {resp.text}")
    except Exception as e:
        print(f"[!] Telegram ni dosegljiv: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Podarimo.si monitor — zaganjan")

    seen, sha = load_seen()
    first_run = len(seen) == 0

    all_ads = []
    for page in PAGES:
        all_ads.extend(fetch_ads(page))

    print(f"[*] Najdenih {len(all_ads)} oglasov na strani")

    if first_run:
        print("[*] Prvo zaganjanje — shranjujem obstoječe oglase...")
        for ad in all_ads:
            seen.add(ad["id"])
        save_seen(seen, sha)
        send_telegram("✅ Podarimo.si monitor zagnan!\nPošiljal ti bom nove oglase. 🎁")
        return

    new_ads = [ad for ad in all_ads if ad["id"] not in seen]

    if new_ads:
        print(f"[+] {len(new_ads)} novih oglasov!")
        for ad in new_ads:
            seen.add(ad["id"])
            print(f"    * {ad['title'][:60]}")
            send_telegram(f"🎁 <b>Nov oglas na podarimo.si!</b>\n\n{ad['title'][:80]}\n\n{ad['url']}")
            time.sleep(1)
        save_seen(seen, sha)
    else:
        print("[~] Ni novih oglasov.")


if __name__ == "__main__":
    main()
