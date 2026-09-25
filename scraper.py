import time
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

BASE_URL = "https://live07.chuoichientv.me"
REFERER_URL = "https://live.chuoichien.tv/"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Chuối Chiên TV"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Bảng ánh xạ Server Stream chuẩn theo tên BLV
CASTER_STREAM_MAP = {
    "troctru": "https://stm9ee346727718.stream.hdplaylink.com/cctvlive/troctruhd/playlist.m3u8",
    "chuoinho": "https://gckc0525.edgemaxcdn.org/live/chuoinhohd/playlist.m3u8",
    "chuoikem": "https://stm9ee346727718.stream.hdplaylink.com/cctvlive/chuoikemhd/playlist.m3u8",
    "chuoisay": "https://gckc0525.edgemaxcdn.org/live/chuoisayhd/playlist.m3u8",
    "chuoichao": "https://stm9ee346727718.stream.hdplaylink.com/cctvlive/chuoichaohd/playlist.m3u8",
    "chuoila": "https://stm9ee346727718.stream.hdplaylink.com/cctvlive/chuoilahd/playlist.m3u8",
    "chuoingao": "https://stm9ee346727718.stream.hdplaylink.com/cctvlive/chuoingaohd/playlist.m3u8",
    "chuoito": "https://stm9ee346727718.stream.hdplaylink.com/cctvlive/chuoitohd/playlist.m3u8",
    "chuoitay": "https://stm9ee346727718.stream.hdplaylink.com/cctvlive/chuoitayhd/playlist.m3u8",
}

KNOWN_BLVS = [
    "Trốc Tru", "Chuối Nhỏ", "Chuối Kem", "Chuối Sấy", "Chuối Chao", 
    "Chuối Lá", "Chuối Ngao", "Chuối To", "Chuối Tây", "Chuối Lập", "Chuối Kỷ", "Chuối Béo"
]

DEFAULT_LOGO = "https://media.chuoichientv.net/media/20250829_080231_89f500ea.gif"

def to_slug(text: str) -> str:
    """Chuyển đổi chuỗi tiếng Việt có dấu thành slug không dấu"""
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.lower().replace('đ', 'd')
    return re.sub(r'[^a-z0-9]', '', text)

def clean_word(w: str) -> str:
    w_low = w.lower()
    if w_low in ['nu', 'nữ', 'women']: return 'W' if w_low in ['nu', 'nữ'] else 'Women'
    if w_low in ['nam', 'men']: return 'Men'
    if w_low in ['u23', 'u21', 'u20', 'u19', 'u18', 'u17', 'u16']: return w.upper()
    return w.capitalize()

def parse_match_details(url: str, card_text: str, page_title: str = ""):
    combined_text = f"{page_title} {card_text}"
    
    # 1. Nhận diện môn thể thao
    sport_icon = "⚽"
    text_lower = combined_text.lower()
    if any(k in text_lower for k in ["bóng chuyền", "volleyball", "🏐"]):
        sport_icon = "🏐"
    elif any(k in text_lower for k in ["bóng rổ", "basketball", "🏀"]):
        sport_icon = "🏀"
    elif any(k in text_lower for k in ["tennis", "quần vợt", "🎾"]):
        sport_icon = "🎾"
    elif any(k in text_lower for k in ["cầu lông", "badminton", "🏸"]):
        sport_icon = "🏸"

    # 2. Bóc tách tên BLV
    blv_name = ""
    for b in KNOWN_BLVS:
        if b.lower() in combined_text.lower() or to_slug(b) in url.lower():
            blv_name = b
            break
            
    if not blv_name:
        match_blv = re.search(r'\(([^)]+)\)', card_text)
        if match_blv:
            val = match_blv.group(1).strip()
            if not any(k in val.lower() for k in ["fhd", "hls", "flv", "hd", "geo"]):
                blv_name = val

    if not blv_name:
        blv_name = "Chuối Chiên"

    # 3. Bóc tách tên 2 đội bóng
    teams_title = ""
    vs_match = re.search(r'([A-Za-zÀ-ỹ0-9\s\.]{2,30})\s+vs\s+([A-Za-zÀ-ỹ0-9\s\.]{2,30})', combined_text, re.I)
    if vs_match:
        t1 = vs_match.group(1).strip().title()
        t2 = vs_match.group(2).strip().title()
        t1 = re.sub(r'^(Trực Tiếp|Xem|Bóng Đá|Trận|Fhd|Hls|Flv)\s*', '', t1, flags=re.I).strip()
        if t1 and t2 and len(t1) > 1 and len(t2) > 1:
            teams_title = f"{t1} vs {t2}"

    if not teams_title:
        try:
            match_slug = re.search(r'/(?:truc-tiep|match|live|room|xem|phong|link|stream)/([^/?#]+)', url)
            slug = match_slug.group(1) if match_slug else url.split('/')[-1]
            
            if '-vs-' in slug:
                parts = slug.split('-vs-')
                t1_slug, t2_slug = parts[0], parts[1]

                t1_slug = re.sub(r'^(?:blv|caster|troc|chuoi|nho|kem|say|ga|ly|chao|la|ngao|to|tay)-[a-z0-9]+-', '', t1_slug, flags=re.I)
                t1_slug = re.sub(r'^(?:blv|caster|troc-tru|chuoi-nho|chuoi-chao|chuoi-la|chuoi-ngao|chuoi-kem|chuoi-say|chuoi-to|chuoi-tay)-', '', t1_slug, flags=re.I)
                t1_slug = re.sub(r'^(?:truc-tiep|xem-truc-tiep|match|live)-', '', t1_slug, flags=re.I)

                t2_slug = re.sub(r'-(?:luc|ngay|[a-z0-9]{8,}).*$', '', t2_slug, flags=re.I)
                t2_slug = re.sub(r'-\d{3,4}$', '', t2_slug, flags=re.I)

                t1 = " ".join([clean_word(w) for w in t1_slug.split('-') if w])
                t2 = " ".join([clean_word(w) for w in t2_slug.split('-') if w])

                if t1 and t2:
                    teams_title = f"{t1} vs {t2}"
        except Exception:
            pass

    if not teams_title:
        teams_title = "Trận đấu Trực Tiếp"

    return sport_icon, teams_title, blv_name

def extract_real_m3u8(context, match_url, blv_name):
    """Bắt link .m3u8 thực tế hoặc fallback theo luồng chuẩn của BLV"""
    page = None
    captured_urls = []
    page_title = ""
    
    try:
        page = context.new_page()
        page.route("**/*.{png,jpg,jpeg,svg,css,woff,woff2}", lambda route: route.abort())

        def handle_request(req):
            u = req.url
            if ".m3u8" in u and "blob:" not in u and u not in captured_urls:
                captured_urls.append(u)

        page.on("request", handle_request)
        page.goto(match_url, timeout=10000, wait_until="domcontentloaded")
        time.sleep(0.8)
        page_title = page.title()

        for _ in range(4):
            if captured_urls:
                break
            time.sleep(0.3)
    except Exception:
        pass
    finally:
        if page:
            try:
                page.close()
            except Exception:
                pass

    if captured_urls:
        return page_title, captured_urls[0]

    # Fallback theo cấu trúc server chuẩn nếu không bắt được luồng động
    slug = to_slug(blv_name)
    fallback_url = CASTER_STREAM_MAP.get(
        slug, 
        f"https://stm9ee346727718.stream.hdplaylink.com/cctvlive/{slug}hd/playlist.m3u8"
    )
    return page_title, fallback_url

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
                time.sleep(0.3)

            # Quét danh sách trận từ Trang chủ
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

                    const img = container.querySelector('img');
                    let logoUrl = '';
                    if (img) {
                        logoUrl = img.getAttribute('src') || img.getAttribute('data-src') || '';
                        if (logoUrl && !logoUrl.startsWith('http')) {
                            logoUrl = window.location.origin + logoUrl;
                        }
                    }

                    const html = container.innerHTML.toLowerCase();
                    const text = container.innerText || card.innerText || '';
                    const isLive = html.includes('live') || html.includes('dang-truc-tiep') || text.toLowerCase().includes('đang trực tiếp');

                    results.push({
                        url: fullUrl,
                        rawText: text,
                        logo: logoUrl,
                        isLive: isLive
                    });
                });
                return results;
            }''')

            page.close()
            print(f"[*] Đã bóc tách {len(raw_matches)} trận. Tiến hành xử lý luồng & dữ liệu...")

            for item in raw_matches:
                match_url = item['url']
                card_text = item['rawText']
                card_logo = item['logo'] if item['logo'] else DEFAULT_LOGO
                is_live = item['isLive']

                # Lấy tên BLV sơ bộ từ Card
                _, initial_blv = parse_match_details(match_url, card_text)

                # Mở trang để lấy .m3u8 thực tế
                page_title, m3u8_stream = extract_real_m3u8(context, match_url, initial_blv)

                sport_icon, teams_title, blv_name = parse_match_details(match_url, card_text, page_title)

                # Giờ & Ngày
                time_match = re.search(r'\b(2[0-3]|[0-1]?\d)[:h](\d{2})\b', card_text, re.I)
                if not time_match:
                    time_match = re.search(r'(?:luc|time)?[-_]?(2[0-3]|[0-1]\d)(\d{2})', match_url, re.I)
                extracted_time = f"{time_match.group(1).zfill(2)}:{time_match.group(2)}" if time_match else "19:00"

                date_match = re.search(r'ngay-(\d{1,2})[-_](\d{1,2})', match_url, re.I)
                match_date = f"{date_match.group(1).zfill(2)}/{date_match.group(2).zfill(2)}" if date_match else today_str

                # Ghép tiêu đề đúng chuẩn 100% mẫu M3U web
                live_dot = "🟢 " if is_live else ""
                full_title = f"{live_dot}{extracted_time} {match_date} {sport_icon} {teams_title} ({blv_name}) [FHD] [hls]"

                try:
                    d, m = map(int, match_date.split('/'))
                    h, mins = map(int, extracted_time.split(':'))
                    dt_obj = datetime(datetime.now(vn_tz).year, m, d, h, mins, tzinfo=vn_tz)
                except Exception:
                    dt_obj = datetime(2099, 1, 1, 0, 0, tzinfo=vn_tz)

                parsed_items.append({
                    "title": full_title,
                    "logo": card_logo,
                    "stream_url": m3u8_stream,
                    "dt": dt_obj,
                    "is_live": is_live,
                    "match_url": match_url
                })

            parsed_items.sort(key=lambda x: (not x['is_live'], x['dt'].date(), x['dt'].time()))
            browser.close()

    except Exception as e:
        print(f"[!] Lỗi tiến trình Playwright: {e}")

    # GHI FILE M3U CHUẨN ĐÚNG CẤU TRÚC MẪU
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write('#EXTM3U\n\n')
        seen_urls = set()
        for item in parsed_items:
            if item['match_url'] in seen_urls:
                continue
            seen_urls.add(item['match_url'])

            f.write(f'#EXTINF:-1 tvg-logo="{item["logo"]}" group-title="{GROUP_NAME}" , {item["title"]} \n')
            f.write(f'#EXTVLCOPT:http-referrer={REFERER_URL}\n')
            f.write(f'{item["stream_url"]}\n\n')

    print(f"[*] Xuất hoàn tất {len(parsed_items)} trận vào file {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
