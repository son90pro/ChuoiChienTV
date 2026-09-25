import time
import re
import sys
from datetime import datetime, timezone, timedelta
from urllib.parse import quote, urljoin
from playwright.sync_api import sync_playwright

WORKER_DOMAIN = "chuoi-chien-iptv.sonnguyen90pro.workers.dev"
BASE_URL = "https://live07.chuoichientv.me"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Chuối Chiên TV"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Bảng tra cứu cờ quốc gia & Logo
LOGOS = {
    "netherlands": "https://flagcdn.com/w320/nl.png", "hà lan": "https://flagcdn.com/w320/nl.png",
    "germany": "https://flagcdn.com/w320/de.png", "đức": "https://flagcdn.com/w320/de.png",
    "spain": "https://flagcdn.com/w320/es.png", "tây ban nha": "https://flagcdn.com/w320/es.png",
    "france": "https://flagcdn.com/w320/fr.png", "pháp": "https://flagcdn.com/w320/fr.png",
    "italy": "https://flagcdn.com/w320/it.png", "ý": "https://flagcdn.com/w320/it.png",
    "portugal": "https://flagcdn.com/w320/pt.png", "bồ đào nha": "https://flagcdn.com/w320/pt.png",
    "england": "https://flagcdn.com/w320/gb-eng.png", "anh": "https://flagcdn.com/w320/gb-eng.png",
    "slovakia": "https://flagcdn.com/w320/sk.png", "armenia": "https://flagcdn.com/w320/am.png", 
    "latvia": "https://flagcdn.com/w320/lv.png", "vietnam": "https://flagcdn.com/w320/vn.png", 
    "việt nam": "https://flagcdn.com/w320/vn.png", "thailand": "https://flagcdn.com/w320/th.png", 
    "thái lan": "https://flagcdn.com/w320/th.png", "indonesia": "https://flagcdn.com/w320/id.png", 
    "malaysia": "https://flagcdn.com/w320/my.png", "japan": "https://flagcdn.com/w320/jp.png", 
    "nhật bản": "https://flagcdn.com/w320/jp.png", "south korea": "https://flagcdn.com/w320/kr.png", 
    "hàn quốc": "https://flagcdn.com/w320/kr.png", "china": "https://flagcdn.com/w320/cn.png", 
    "trung quốc": "https://flagcdn.com/w320/cn.png", "india": "https://flagcdn.com/w320/in.png", 
    "panama": "https://flagcdn.com/w320/pa.png", "brazil": "https://flagcdn.com/w320/br.png", 
    "argentina": "https://flagcdn.com/w320/ar.png", "singapore": "https://flagcdn.com/w320/sg.png",
    "turkiye": "https://flagcdn.com/w320/tr.png", "thổ nhĩ kỳ": "https://flagcdn.com/w320/tr.png",
    "belgium": "https://flagcdn.com/w320/be.png", "bỉ": "https://flagcdn.com/w320/be.png",
    "poland": "https://flagcdn.com/w320/pl.png", "ba lan": "https://flagcdn.com/w320/pl.png"
}

def clean_word(w: str) -> str:
    w_low = w.lower()
    if w_low in ['nu', 'nữ', 'women']: return 'Nữ'
    if w_low in ['nam', 'men']: return 'Nam'
    if w_low in ['u23', 'u21', 'u20', 'u19', 'u18', 'u17', 'u16']: return w.upper()
    return w.capitalize()

def get_team_logo(teams_str: str, raw_logo: str = "") -> str:
    if raw_logo and raw_logo.startswith("http") and "un.png" not in raw_logo:
        return raw_logo
    t_lower = teams_str.lower()
    for key, url in LOGOS.items():
        if key in t_lower:
            return url
    return "https://flagcdn.com/w320/un.png"

def parse_teams_from_slug_or_text(url: str, card_text: str) -> str:
    # Quét tên 2 đội bóng từ text card
    vs_match = re.search(r'([A-Za-zÀ-ỹ0-9\s]+)\s+vs\s+([A-Za-zÀ-ỹ0-9\s]+)', card_text, re.I)
    if vs_match:
        t1 = vs_match.group(1).strip().title()
        t2 = vs_match.group(2).strip().title()
        if len(t1) > 1 and len(t2) > 1:
            return f"{t1} vs {t2}"

    # Quét tên 2 đội từ URL slug
    try:
        match = re.search(r'/(?:truc-tiep|match|live|room|xem|phong|link|stream)/([^/?#]+)', url)
        if match:
            slug = match.group(1)
            if '-vs-' in slug:
                parts = slug.split('-vs-')
                t1_raw = re.sub(r'^(?:blv|caster|troc|chuoi|nho|kem|say|ga|ly)-[a-z0-9]+-', '', parts[0], flags=re.I)
                t1_raw = re.sub(r'^(?:blv|caster)-', '', t1_raw, flags=re.I)
                
                t2_raw = re.sub(r'-(?:luc|ngay|[a-z0-9]{8,}).*$', '', parts[1], flags=re.I)
                
                t1 = " ".join([clean_word(w) for w in t1_raw.split('-') if w])
                t2 = " ".join([clean_word(w) for w in t2_raw.split('-') if w])
                if t1 and t2:
                    return f"{t1} vs {t2}"
    except Exception:
        pass
    return ""

def parse_blv_name(card_text: str, url: str) -> str:
    # Ưu tiên lấy từ ngoặc đơn trong text
    match = re.search(r'\(([^)]+)\)', card_text)
    if match:
        found_blv = match.group(1).strip()
        if not any(k in found_blv.lower() for k in ["fhd", "hls", "flv", "hd"]):
            return found_blv

    # Quét từ từ khóa BLV trong text
    blv_match = re.search(r'((?:Chuối|Trốc|BLV|Caster|Gà|Lý)\s+[A-Za-zÀ-ỹ0-9\s\+]+)', card_text, re.I)
    if blv_match:
        raw_blv = blv_match.group(1).strip()
        clean_blv = re.split(r'(?:hls|flv|live|trực tiếp|\d{1,2}:\d{2}|hiệp|cúp|league|\[|\()', raw_blv, flags=re.I)[0].strip()
        if clean_blv:
            return re.sub(r'^(BLV|Caster)\s*[:\-]?\s*', '', clean_blv, flags=re.I).strip()

    # Quét từ đường dẫn Slug
    slug_blv = re.search(r'/(?:blv|caster|troc|chuoi|ga|ly)-([a-z0-9-]+?)-(?:vs|[a-z0-9]+-vs)', url, re.I)
    if slug_blv:
        return slug_blv.group(1).replace('-', ' ').title()

    return "Chuối Chiên"

def extract_stream_m3u8(context, match_url):
    page = None
    captured_urls = []
    try:
        page = context.new_page()
        page.route("**/*.{png,jpg,jpeg,svg,css,woff,woff2}", lambda route: route.abort())

        def handle_request(req):
            u = req.url
            if (".m3u8" in u or ".flv" in u) and "blob:" not in u and u not in captured_urls:
                captured_urls.append(u)

        page.on("request", handle_request)
        page.goto(match_url, timeout=10000, wait_until="domcontentloaded")
        time.sleep(1)

        for selector in ["iframe", "video", ".play-btn", "button:has-text('HD1')", "button:has-text('HD2')"]:
            try:
                el = page.query_selector(selector)
                if el:
                    el.click(timeout=600)
                    time.sleep(0.3)
            except Exception:
                pass

        for _ in range(5):
            if captured_urls:
                break
            time.sleep(0.3)

        if not captured_urls:
            for frame in page.frames:
                try:
                    content = frame.content()
                    urls = re.findall(r'https?://[^\s"\'<>]+\.(?:m3u8|flv)[^\s"\'<>]*', content)
                    for u in urls:
                        if "blob:" not in u and u not in captured_urls:
                            captured_urls.append(u)
                except Exception:
                    pass
    except Exception:
        pass
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass

    return captured_urls[0] if captured_urls else ""

def run_scraper():
    vn_tz = timezone(timedelta(hours=7))
    today_str = datetime.now(vn_tz).strftime("%d/%m")
    parsed_items = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-setuid-sandbox"]
            )
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 720},
                timezone_id="Asia/Ho_Chi_Minh",
                locale="vi-VN"
            )
            page = context.new_page()

            print(f"[*] Kết nối tới: {BASE_URL}")
            page.goto(BASE_URL, timeout=45000, wait_until="domcontentloaded")
            time.sleep(2)

            for _ in range(3):
                page.evaluate("window.scrollBy(0, 800)")
                time.sleep(0.4)

            raw_matches = page.evaluate('''() => {
                const results = [];
                const selector = 'a[href*="/truc-tiep/"], a[href*="/match/"], a[href*="/live/"], a[href*="/xem/"], a[href*="/room/"], a[href*="/phong/"]';
                const cards = document.querySelectorAll(selector);
                const seenUrls = new Set();

                cards.forEach(card => {
                    const href = card.getAttribute('href');
                    if (!href) return;
                    const fullUrl = href.startsWith('http') ? href : window.location.origin + href;
                    if (seenUrls.has(fullUrl)) return;
                    seenUrls.add(fullUrl);

                    let container = card;
                    let parent = card.parentElement;
                    while (parent && parent.tagName !== 'BODY') {
                        if (parent.querySelectorAll(selector).length > 1) break;
                        container = parent;
                        parent = parent.parentElement;
                    }

                    const homeEl = container.querySelector('.home-name, .team-home, .team1, .home, .name-home');
                    const awayEl = container.querySelector('.away-name, .team-away, .team2, .away, .name-away');
                    const blvEl = container.querySelector('.blv, .caster, .commentator, .author, .speaker');
                    const timeEl = container.querySelector('.time, .match-time, .start-time');
                    const imgEl = container.querySelector('img');

                    results.push({
                        url: fullUrl,
                        rawText: container.innerText || card.innerText || '',
                        homeName: homeEl ? homeEl.innerText.trim() : '',
                        awayName: awayEl ? awayEl.innerText.trim() : '',
                        blvName: blvEl ? blvEl.innerText.trim() : '',
                        timeStr: timeEl ? timeEl.innerText.trim() : '',
                        logo: imgEl ? (imgEl.src || imgEl.getAttribute('data-src') || '') : ''
                    });
                });
                return results;
            }''')

            page.close()
            print(f"[*] Quét được {len(raw_matches)} trận. Đang tiến hành bóc tách...")

            for item in raw_matches:
                try:
                    match_url = item['url']
                    card_text = item['rawText']

                    # 1. TÊN ĐỘI BÓNG
                    teams_title = ""
                    if item['homeName'] and item['awayName']:
                        teams_title = f"{item['homeName']} vs {item['awayName']}"
                    else:
                        teams_title = parse_teams_from_slug_or_text(match_url, card_text)

                    if not teams_title:
                        teams_title = "Trận đấu Trực Tiếp"

                    # 2. TÊN BLV
                    blv_name = item['blvName'] if item['blvName'] else parse_blv_name(card_text, match_url)

                    # 3. GIỜ & NGÀY
                    time_match = re.search(r'\b(2[0-3]|[0-1]?\d)[:h](\d{2})\b', item['timeStr'] if item['timeStr'] else card_text, re.I)
                    if not time_match:
                        time_match = re.search(r'(?:luc|time)?[-_]?(2[0-3]|[0-1]\d)(\d{2})', match_url, re.I)
                    extracted_time = f"{time_match.group(1).zfill(2)}:{time_match.group(2)}" if time_match else "19:00"

                    date_match = re.search(r'ngay-(\d{1,2})[-_](\d{1,2})', match_url, re.I)
                    match_date = f"{date_match.group(1).zfill(2)}/{date_match.group(2).zfill(2)}" if date_match else today_str

                    # 4. TRÍCH XUẤT STREAM & LOGO
                    m3u8_url = extract_stream_m3u8(context, match_url)
                    final_logo = get_team_logo(teams_title, item['logo'])
                    stream_type = "[flv]" if "flv" in match_url.lower() or "flv" in m3u8_url.lower() else "[hls]"

                    full_title = f"{extracted_time} {match_date} ⚽ {teams_title} ({blv_name}) [FHD] {stream_type}"

                    try:
                        d, m = map(int, match_date.split('/'))
                        h, mins = map(int, extracted_time.split(':'))
                        dt_obj = datetime(datetime.now(vn_tz).year, m, d, h, mins, tzinfo=vn_tz)
                    except Exception:
                        dt_obj = datetime(2099, 1, 1, 0, 0, tzinfo=vn_tz)

                    playable_stream = m3u8_url if m3u8_url else match_url

                    parsed_items.append({
                        "title": full_title,
                        "logo": final_logo,
                        "stream_url": playable_stream,
                        "is_live": bool(m3u8_url),
                        "dt": dt_obj,
                        "match_url": match_url
                    })
                except Exception as item_err:
                    print(f"[!] Bỏ qua 1 trận do lỗi: {item_err}")
                    continue

            parsed_items.sort(key=lambda x: (x['dt'].date(), not x['is_live'], x['dt'].time()))
            browser.close()

    except Exception as e:
        print(f"[!] Lỗi tiến trình Playwright: {e}")

    # GHI FILE M3U
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write('#EXTM3U\n\n')
        seen_urls = set()
        for item in parsed_items:
            if item['match_url'] in seen_urls:
                continue
            seen_urls.add(item['match_url'])

            logo_attr = f'tvg-logo="{item["logo"]}"' if item["logo"] else ''
            
            # Nếu là link m3u8 trực tiếp thì thêm proxy worker để chống chặn
            if item["stream_url"].endswith(".m3u8") or item["stream_url"].endswith(".flv"):
                final_link = f"https://{WORKER_DOMAIN}/proxy?url={quote(item['stream_url'], safe='')}"
            else:
                final_link = f"https://{WORKER_DOMAIN}/live?url={quote(item['stream_url'], safe='')}"

            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}" , {item["title"]} \n')
            f.write(f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n')
            f.write(f'#EXTVLCOPT:http-referrer={BASE_URL}/\n')
            f.write(f'{final_link}|User-Agent={USER_AGENT}&Referer={BASE_URL}/\n\n')

    print(f"[*] Xuất hoàn tất {len(parsed_items)} trận vào file {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
