import time
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import quote, urljoin
from playwright.sync_api import sync_playwright

BASE_URL = "https://live07.chuoichientv.me"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Chuối Chiên TV"

# Bảng tra cứu cờ quốc gia chuẩn hóa
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
    "argentina": "https://flagcdn.com/w320/ar.png", "singapore": "https://flagcdn.com/w320/sg.png"
}

def get_team_logo_url(teams_str: str) -> str:
    t_lower = teams_str.lower()
    for key, url in LOGOS.items():
        if key in t_lower:
            return url
    return "https://flagcdn.com/w320/un.png"

def clean_team_name(name: str) -> str:
    if not name:
        return ""
    s = re.sub(r'^(?:blv|caster|troc|chuoi|nho|kem|say)-[a-z0-9]+-', '', name, flags=re.I)
    s = re.sub(r'-(?:luc|ngay|[a-z0-9]{8,}).*$', '', s, flags=re.I)
    return s.replace('-', ' ').strip().title()

def parse_teams_from_text_or_url(url: str, text: str) -> str:
    # 1. Thử quét trực tiếp từ text hiển thị trên card (Ví dụ: "Indonesia vs Singapore")
    vs_match = re.search(r'([A-Za-zÀ-ỹ0-9\s]+)\s+vs\s+([A-Za-zÀ-ỹ0-9\s]+)', text, re.I)
    if vs_match:
        t1 = vs_match.group(1).strip().title()
        t2 = vs_match.group(2).strip().title()
        if len(t1) > 1 and len(t2) > 1:
            return f"{t1} vs {t2}"

    # 2. Quét từ URL Slug
    try:
        match = re.search(r'/(?:truc-tiep|match|live|room|xem|phong|link|stream)/([^/?#]+)', url)
        if match:
            slug = match.group(1)
            if '-vs-' in slug:
                parts = slug.split('-vs-')
                t1 = clean_team_name(parts[0])
                t2 = clean_team_name(parts[1])
                if t1 and t2:
                    return f"{t1} vs {t2}"
    except Exception:
        pass
    return ""

def parse_time_and_date(url: str, text: str, default_date: str):
    # Tìm giờ dạng HH:MM hoặc HHhMM
    time_match = re.search(r'\b(2[0-3]|[0-1]?\d)[:h](\d{2})\b', text, re.I)
    if not time_match:
        time_match = re.search(r'(?:luc|time)?[-_]?(2[0-3]|[0-1]\d)(\d{2})', url, re.I)
    
    time_str = f"{time_match.group(1).zfill(2)}:{time_match.group(2)}" if time_match else "19:00"

    # Tìm ngày
    date_match = re.search(r'ngay-(\d{1,2})[-_](\d{1,2})', url, re.I)
    if date_match:
        date_str = f"{date_match.group(1).zfill(2)}/{date_match.group(2).zfill(2)}"
    else:
        text_date = re.search(r'\b(\d{1,2})[/.-](\d{1,2})\b', text)
        date_str = f"{text_date.group(1).zfill(2)}/{text_date.group(2).zfill(2)}" if text_date else default_date

    return time_str, date_str

def parse_blv_name(text: str, url: str) -> str:
    match = re.search(r'\(([^)]+)\)', text)
    if match:
        return match.group(1).strip()
    
    slug_blv = re.search(r'/(?:blv|caster|troc|chuoi)-([a-z0-9-]+?)-', url, re.I)
    if slug_blv:
        return slug_blv.group(1).replace('-', ' ').title()
    return "Trốc Tru"

def extract_stream_m3u8(context, match_url):
    page = context.new_page()
    captured_urls = []
    
    def handle_request(req):
        u = req.url
        if (".m3u8" in u or ".flv" in u) and "blob:" not in u and u not in captured_urls:
            captured_urls.append(u)

    page.on("request", handle_request)
    
    try:
        page.goto(match_url, timeout=10000, wait_until="domcontentloaded")
        time.sleep(1)

        for selector in ["iframe", "video", ".play-btn", "button:has-text('HD1')", "button:has-text('HD2')", ".vjs-big-play-button"]:
            try:
                el = page.query_selector(selector)
                if el:
                    el.click(timeout=800)
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
                    m3u8_matches = re.findall(r'https?://[^\s"\'<>]+\.(?:m3u8|flv)[^\s"\'<>]*', content)
                    for m_url in m3u8_matches:
                        if "blob:" not in m_url and m_url not in captured_urls:
                            captured_urls.append(m_url)
                except Exception:
                    pass
    except Exception:
        pass
    finally:
        page.close()

    return captured_urls[0] if captured_urls else ""

def run_scraper():
    vn_tz = timezone(timedelta(hours=7))
    today_str = datetime.now(vn_tz).strftime("%d/%m")
    final_matches = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            timezone_id="Asia/Ho_Chi_Minh",
            locale="vi-VN"
        )
        page = context.new_page()

        try:
            print(f"[*] Đang tải trang: {BASE_URL}")
            page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
            time.sleep(2)

            for _ in range(3):
                page.evaluate("window.scrollBy(0, 800)")
                time.sleep(0.4)

            raw_cards = page.evaluate('''() => {
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

                    results.push({
                        url: fullUrl,
                        rawText: container.innerText || card.innerText || ''
                    });
                });
                return results;
            }''')

            page.close()
            print(f"[*] Quét được {len(raw_cards)} trận. Đang lấy link stream và tên đội...")

            for item in raw_cards:
                match_url = item['url']
                card_text = item['rawText']

                teams_str = parse_teams_from_text_or_url(match_url, card_text)
                if not teams_str:
                    teams_str = "Trận đấu Trực Tiếp"

                logo = get_team_logo_url(teams_str)
                m3u8_url = extract_stream_m3u8(context, match_url)

                time_str, date_str = parse_time_and_date(match_url, card_text, today_str)
                blv_name = parse_blv_name(card_text, match_url)

                is_live = bool(m3u8_url) or bool(re.search(r'(hiệp 1|hiệp 2|đang đá|đang diễn ra|live)', card_text, re.I))
                stream_type = "[flv]" if "flv" in match_url.lower() else "[hls]"

                # Định dạng tiêu đề chuẩn: 20:00 25/09 ⚽ Indonesia vs Singapore (Trốc Tru) [FHD] [hls]
                full_title = f"{time_str} {date_str} ⚽ {teams_str} ({blv_name}) [FHD] {stream_type}"

                try:
                    d, m = map(int, date_str.split('/'))
                    h, mins = map(int, time_str.split(':'))
                    yr = datetime.now(vn_tz).year
                    dt_obj = datetime(yr, m, d, h, mins, tzinfo=vn_tz)
                except:
                    dt_obj = datetime(2099, 1, 1, 0, 0, tzinfo=vn_tz)

                final_stream = m3u8_url if m3u8_url else match_url

                final_matches.append({
                    "title": full_title,
                    "logo": logo,
                    "stream_url": final_stream,
                    "is_live": is_live,
                    "dt": dt_obj
                })

            # Sắp xếp: Ngày hôm nay lên đầu -> Trận LIVE -> Giờ thi đấu
            final_matches.sort(key=lambda x: (x['dt'].date(), not x['is_live'], x['dt'].time()))

        except Exception as e:
            print(f"[!] Lỗi: {e}")
        finally:
            browser.close()

    # Xuất file M3U chuẩn định dạng
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write('#EXTM3U\n\n')
        for item in final_matches:
            logo_attr = f'tvg-logo="{item["logo"]}"' if item["logo"] else ''
            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}" , {item["title"]} \n')
            f.write(f'#EXTVLCOPT:http-referrer={BASE_URL}/\n')
            f.write(f'{item["stream_url"]}\n\n')

    print(f"[*] Xuất hoàn tất {len(final_matches)} trận vào {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
