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

# Bảng ánh xạ Server CDN chuẩn từng BLV (Đã khớp 100% domain hdplaylink & edgemaxcdn)
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
    "chuoilap": "https://stm9ee346727718.stream.hdplaylink.com/cctvlive/chuoilaphd/playlist.m3u8",
    "chuoiky": "https://stm9ee346727718.stream.hdplaylink.com/cctvlive/chuoikyhd/playlist.m3u8",
    "chuoibeo": "https://stm9ee346727718.stream.hdplaylink.com/cctvlive/chuoibeohd/playlist.m3u8",
}

KNOWN_BLVS = [
    "Trốc Tru", "Chuối Nhỏ", "Chuối Kem", "Chuối Sấy", "Chuối Chao", 
    "Chuối Lá", "Chuối Ngao", "Chuối To", "Chuối Tây", "Chuối Lập", "Chuối Kỷ", "Chuối Béo"
]

DEFAULT_LOGO = "https://media.chuoichientv.net/media/20250829_080231_89f500ea.gif"

def to_slug(text: str) -> str:
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.lower().replace('đ', 'd')
    return re.sub(r'[^a-z0-9]', '', text)

def clean_word(w: str) -> str:
    w_low = w.lower()
    if w_low in ['nu', 'nữ', 'women']: return 'W'
    if w_low in ['nam', 'men']: return 'Men'
    if w_low in ['u23', 'u21', 'u20', 'u19', 'u18', 'u17', 'u16']: return w.upper()
    return w.capitalize()

def extract_teams_from_slug(url: str) -> str:
    """Giải mã tên 2 đội từ đường dẫn URL nếu trang web không ghi chữ 'vs'"""
    try:
        match_slug = re.search(r'/(?:truc-tiep|match|live|room|xem|phong|link|stream)/([^/?#]+)', url)
        if not match_slug:
            return ""
        slug = match_slug.group(1).lower()
        if '-vs-' in slug:
            parts = slug.split('-vs-')
            left = parts[0]
            right = parts[1]

            left = re.sub(r'^(?:blv|caster|troc|chuoi|nho|kem|say|ga|ly|chao|la|ngao|to|tay|truc-tiep|xem-truc-tiep|match|live)-', '', left)
            left = re.sub(r'^[a-z0-9]+-', '', left) if len(left.split('-')) > 3 else left
            
            right = re.sub(r'-(?:luc|ngay|time|fhd|hls|\d{2}h\d{2}|\d{3,4}|\d{1,2}-\d{1,2}|\d{4}).*$', '', right)

            t1 = " ".join([clean_word(w) for w in left.split('-') if w and not w.isdigit()])
            t2 = " ".join([clean_word(w) for w in right.split('-') if w and not w.isdigit()])

            if t1 and t2:
                return f"{t1} vs {t2}"
    except Exception:
        pass
    return ""

def extract_teams_from_text(card_text: str) -> str:
    """Tự động bóc tách 2 dòng tên đội bóng từ văn bản thẻ trận đấu"""
    lines = [line.strip() for line in card_text.split('\n') if line.strip()]
    cleaned_lines = []
    for line in lines:
        l_lower = line.lower()
        if re.search(r'^\d{1,2}[:h]\d{2}$', line) or re.search(r'^\d{1,2}/\d{1,2}', line):
            continue
        if any(k in l_lower for k in ['fhd', 'hls', 'live', 'đang trực tiếp', 'chuối', 'trốc', 'blv', 'caster']):
            continue
        if len(line) < 2 or len(line) > 35:
            continue
        cleaned_lines.append(line)
    
    if len(cleaned_lines) >= 2:
        return f"{cleaned_lines[0]} vs {cleaned_lines[1]}"
    return ""

def parse_card_info(url: str, card_text: str, dom_t1: str = "", dom_t2: str = ""):
    combined_text = card_text.strip()
    
    # 1. Nhận diện môn thể thao
    sport_icon = "⚽"
    text_lower = combined_text.lower()
    if any(k in text_lower for k in ["bóng chuyền", "volleyball", "🏐"]):
        sport_icon = "🏐"
    elif any(k in text_lower for k in ["bóng rổ", "basketball", "🏀"]):
        sport_icon = "🏀"
    elif any(k in text_lower for k in ["tennis", "quần vợt", "🎾"]):
        sport_icon = "🎾"

    # 2. Bóc tách tên BLV
    blv_name = ""
    for b in KNOWN_BLVS:
        if b.lower() in combined_text.lower() or to_slug(b) in url.lower():
            blv_name = b
            break
            
    if not blv_name:
        match_blv = re.search(r'\(([^)]+)\)', combined_text)
        if match_blv:
            val = match_blv.group(1).strip()
            if not any(k in val.lower() for k in ["fhd", "hls", "flv", "hd", "geo"]):
                blv_name = val

    if not blv_name:
        blv_name = "Chuối Chiên"

    # 3. Trích xuất tên 2 Đội bóng (Thuật toán 3 lớp triệt để)
    teams_title = ""
    
    # Lớp 1: Lấy trực tiếp từ thẻ DOM 2 đội
    if dom_t1 and dom_t2:
        teams_title = f"{dom_t1} vs {dom_t2}"

    # Lớp 2: Tìm chữ 'vs' trong Text
    if not teams_title:
        vs_match = re.search(r'([A-Za-zÀ-ỹ0-9\s\.]{2,30})\s+vs\s+([A-Za-zÀ-ỹ0-9\s\.]{2,30})', combined_text, re.I)
        if vs_match:
            t1 = vs_match.group(1).strip().title()
            t2 = vs_match.group(2).strip().title()
            t1 = re.sub(r'^(Trực Tiếp|Xem|Bóng Đá|Trận|Fhd|Hls|Flv)\s*', '', t1, flags=re.I).strip()
            if t1 and t2 and len(t1) > 1 and len(t2) > 1:
                teams_title = f"{t1} vs {t2}"

    # Lớp 3: Bóc tách từng dòng văn bản
    if not teams_title:
        teams_title = extract_teams_from_text(card_text)

    # Lớp 4: Giải mã URL Slug
    if not teams_title:
        teams_title = extract_teams_from_slug(url)

    if not teams_title:
        teams_title = "Trận đấu Trực Tiếp"

    # 4. Ghép Link Stream tương ứng với BLV
    blv_slug = to_slug(blv_name)
    stream_url = CASTER_STREAM_MAP.get(
        blv_slug, 
        f"https://stm9ee346727718.stream.hdplaylink.com/cctvlive/{blv_slug}hd/playlist.m3u8"
    )

    return sport_icon, teams_title, blv_name, stream_url

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
            print(f"[*] Đang kết nối tới: {BASE_URL}")
            page.goto(BASE_URL, timeout=45000, wait_until="domcontentloaded")
            time.sleep(2)

            # Tự động cuộn trang & Bấm tất cả các Tab để quét 100% số trận
            page.evaluate('''() => {
                window.scrollTo(0, document.body.scrollHeight / 2);
                const tabs = document.querySelectorAll('button, .tab, .menu-item, [class*="tab"]');
                tabs.forEach(tab => {
                    if (tab.innerText && (tab.innerText.includes('Tất cả') || tab.innerText.includes('Hôm nay') || tab.innerText.includes('Trực tiếp'))) {
                        try { tab.click(); } catch(e){}
                    }
                });
            }''')
            time.sleep(1.5)

            for _ in range(4):
                page.evaluate("window.scrollBy(0, 1000)")
                time.sleep(0.3)

            # Quét toàn bộ dữ liệu thẻ trận đấu từ HTML DOM
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

                    // Trích xuất Logo gốc của trận/đội bóng
                    const imgs = container.querySelectorAll('img');
                    let logoUrl = '';
                    imgs.forEach(img => {
                        if (!logoUrl) {
                            const src = img.getAttribute('src') || img.getAttribute('data-src') || img.getAttribute('data-original') || '';
                            if (src && !src.includes('avatar') && !src.includes('icon')) {
                                logoUrl = src;
                            }
                        }
                    });
                    if (logoUrl && logoUrl.startsWith('//')) logoUrl = 'https:' + logoUrl;
                    else if (logoUrl && !logoUrl.startsWith('http')) logoUrl = window.location.origin + logoUrl;

                    // Lấy Tên 2 đội từ các thẻ HTML con
                    const teamEls = container.querySelectorAll('[class*="team"], [class*="club"], [class*="home"], [class*="away"]');
                    let dom_t1 = '', dom_t2 = '';
                    const teamsFound = [];
                    teamEls.forEach(t => {
                        const txt = t.innerText ? t.innerText.trim() : '';
                        if (txt && txt.length > 1 && txt.length < 30 && !txt.includes(':') && !txt.includes('FHD') && !txt.includes('Chuối') && !txt.includes('Trốc')) {
                            if (!teamsFound.includes(txt)) teamsFound.push(txt);
                        }
                    });
                    if (teamsFound.length >= 2) {
                        dom_t1 = teamsFound[0];
                        dom_t2 = teamsFound[1];
                    }

                    const html = container.innerHTML.toLowerCase();
                    const text = container.innerText || card.innerText || '';
                    const isLive = html.includes('live') || html.includes('dang-truc-tiep') || text.toLowerCase().includes('đang trực tiếp');

                    results.push({
                        url: fullUrl,
                        rawText: text,
                        logo: logoUrl,
                        dom_t1: dom_t1,
                        dom_t2: dom_t2,
                        isLive: isLive
                    });
                });
                return results;
            }''')

            page.close()
            browser.close()

            print(f"[*] Đã quét được {len(raw_matches)} trận đấu. Tiến hành bóc tách tên đội & luồng phát...")

            for item in raw_matches:
                match_url = item['url']
                card_text = item['rawText']
                card_logo = item['logo'] if item['logo'] else DEFAULT_LOGO
                is_live = item['isLive']

                sport_icon, teams_title, blv_name, stream_url = parse_card_info(
                    match_url, card_text, item.get('dom_t1', ''), item.get('dom_t2', '')
                )

                # Giờ & Ngày
                time_match = re.search(r'\b(2[0-3]|[0-1]?\d)[:h](\d{2})\b', card_text, re.I)
                if not time_match:
                    time_match = re.search(r'(?:luc|time)?[-_]?(2[0-3]|[0-1]\d)(\d{2})', match_url, re.I)
                extracted_time = f"{time_match.group(1).zfill(2)}:{time_match.group(2)}" if time_match else "19:00"

                date_match = re.search(r'ngay-(\d{1,2})[-_](\d{1,2})', match_url, re.I)
                match_date = f"{date_match.group(1).zfill(2)}/{date_match.group(2).zfill(2)}" if date_match else today_str

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
                    "stream_url": stream_url,
                    "dt": dt_obj,
                    "is_live": is_live,
                    "match_url": match_url
                })

            parsed_items.sort(key=lambda x: (not x['is_live'], x['dt'].date(), x['dt'].time()))

    except Exception as e:
        print(f"[!] Lỗi tiến trình Playwright: {e}")

    # GHI FILE M3U CHUẨN ĐẦU PHÁT TIVIMATE / ANDROID TV BOX
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write('#EXTM3U\n\n')
        seen_urls = set()
        for item in parsed_items:
            if item['match_url'] in seen_urls:
                continue
            seen_urls.add(item['match_url'])

            f.write(f'#EXTINF:-1 tvg-logo="{item["logo"]}" group-title="{GROUP_NAME}" , {item["title"]} \n')
            f.write(f'#EXTVLCOPT:http-referrer={REFERER_URL}\n')
            f.write(f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n')
            f.write(f'{item["stream_url"]}\n\n')

    print(f"[*] Xuất thành công {len(parsed_items)} trận vào {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
