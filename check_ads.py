"""
Podarimo.si - Enkratni preverjalec novih oglasov (za GitHub Actions)
"""

import json
import os
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SEEN_FILE = Path("seen_ads.json")
BASE_URL = "https://www.podarimo.si"

PAGES_TO_MONITOR = [
    f"{BASE_URL}/podarim/vsi-oglasi/stran-1",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}


def load_seen() -> set:
    if SEEN_FILE.exists():
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen)), f)


def fetch_ads(url: str) -> list[dict]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
    except requests.RequestException as e:
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
        slug = match.group(2)
        title = a.get("title") or a.get_text(strip=True) or slug.replace("-", " ")
        if title and len(title) > 2 and ad_id not in seen_ids:
            seen_ids.add(ad_id)
            full_url = href if href.startswith("http") else BASE_URL + href
            ads.append({"id": ad_id, "title": title, "url": full_url})

    return ads


def send_telegram(message: str):
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=10,
        )
        if not resp.ok:
            print(f"[!] Telegram napaka: {resp.text}")
    except Exception as e:
        print(f"[!] Telegram ni dosegljiv: {e}")


def main():
    seen = load_seen()
    first_run = not seen

    all_ads = []
    for page_url in PAGES_TO_MONITOR:
        all_ads.extend(fetch_ads(page_url))

    if first_run:
        print(f"[*] Prvo zaganjanje — shranjujem {len(all_ads)} oglasov.")
        for ad in all_ads:
            seen.add(ad["id"])
        save_seen(seen)
        send_telegram("✅ Monitor zagnan! Posiljal ti bom nove oglase s podarimo.si 🎁")
        return

    new_ads = [ad for ad in all_ads if ad["id"] not in seen]

    if new_ads:
        print(f"[+] {len(new_ads)} novih oglasov!")
        for ad in new_ads:
            seen.add(ad["id"])
            print(f"    * {ad['title'][:60]}")
            msg = f"🎁 <b>Nov oglas na podarimo.si!</b>\n\n{ad['title'][:80]}\n\n{ad['url']}"
            send_telegram(msg)
            time.sleep(1)
        save_seen(seen)
    else:
        print("[~] Ni novih oglasov.")


if __name__ == "__main__":
    main()
