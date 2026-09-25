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

# Bảng ánh xạ Server CDN chuẩn từng BLV
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

def clean_team_name(name: str) -> str:
    """Làm sạch tên đội bóng, giữ nguyên định dạng như mẫu (VD: Slovakia W, Türkiye, India)"""
    if not name:
        return ""
    name = re.sub(r'^\d+[\.\s]*', '', name)
    name = re.sub(r'\s*(FHD|HLS|HD|Live)\s*', '', name, flags=re.I)
    return name.strip()

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

            # Cuộn trang để tải đầy đủ các thẻ trận đấu
            for _ in range(3):
                page.evaluate("window.scrollBy(0, 1000)")
                time.sleep(0.3)

            # Trích xuất dữ liệu thẻ trận đấu trực tiếp từ DOM Web
            raw_matches = page.evaluate('''() => {
                const results = [];
                const selector = 'a[href*="/truc-tiep/"], a[href*="/match/"], a[href*="/live/"], a[href*="/xem/"], a[href*="/room/"]';
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

                    // 1. Tìm Tên 2 Đội từ các phần tử chứa tên đội
                    let team1 = '', team2 = '';
                    const teamEls = container.querySelectorAll('.team-name, .home-name, .away-name, [class*="team"], [class*="club"]');
                    if (teamEls.length >= 2) {
                        team1 = teamEls[0].innerText.trim();
                        team2 = teamEls[1].innerText.trim();
                    }

                    // 2. Lấy Logo/Cờ của Đội 1
                    let logoUrl = '';
                    const imgs = container.querySelectorAll('img');
                    imgs.forEach(img => {
                        if (!logoUrl) {
                            const src = img.getAttribute('src') || img.getAttribute('data-src') || '';
                            if (src && !src.includes('avatar') && !src.includes('icon') && !src.includes('gif')) {
                                logoUrl = src;
                            }
                        }
                    });
                    if (logoUrl && logoUrl.startsWith('//')) logoUrl = 'https:' + logoUrl;
                    else if (logoUrl && !logoUrl.startsWith('http')) logoUrl = window.location.origin + logoUrl;

                    // 3. Trạng thái Live / Chuẩn bị / Sắp tới
                    const textAll = container.innerText || '';
                    const htmlAll = container.innerHTML.toLowerCase();
                    let status = 'upcoming'; // 'live', 'soon', 'upcoming'
                    
                    if (htmlAll.includes('live') || textAll.includes('Đang diễn ra') || textAll.includes('Hiệp 1') || textAll.includes('Hiệp 2')) {
                        status = 'live';
                    } else if (textAll.includes('Sắp diễn ra') || textAll.includes('Chuẩn bị')) {
                        status = 'soon';
                    }

                    results.push({
                        url: fullUrl,
                        rawText: textAll,
                        team1: team1,
                        team2: team2,
                        logo: logoUrl,
                        status: status
                    });
                });
                return results;
            }''')

            page.close()

            print(f"[*] Đã lấy được {len(raw_matches)} trận đấu. Tiến hành định dạng chuẩn M3U...")

            for item in raw_matches:
                match_url = item['url']
                card_text = item['rawText']
                card_logo = item['logo'] if item['logo'] else DEFAULT_LOGO
                status = item['status']

                # Bóc tách tên BLV
                blv_name = "Chuối Chiên"
                for b in KNOWN_BLVS:
                    if b.lower() in card_text.lower() or to_slug(b) in match_url.lower():
                        blv_name = b
                        break

                # Bóc tách tên 2 đội bóng
                t1 = clean_team_name(item['team1'])
                t2 = clean_team_name(item['team2'])
                
                # Nếu DOM không tách sẵn tên đội, bóc từ Chuỗi Text
                if not t1 or not t2:
                    match_vs = re.search(r'([A-Za-zÀ-ỹ0-9\s\.]{2,25})\s+vs\s+([A-Za-zÀ-ỹ0-9\s\.]{2,25})', card_text, re.I)
                    if match_vs:
                        t1 = clean_team_name(match_vs.group(1))
                        t2 = clean_team_name(match_vs.group(2))
                
                teams_title = f"{t1} vs {t2}" if (t1 and t2) else "Trận đấu Trực Tiếp"

                # Nhận diện môn thể thao
                sport_icon = "⚽"
                text_lower = card_text.lower()
                if any(k in text_lower for k in ["bóng chuyền", "volleyball"]):
                    sport_icon = "🏐"
                elif any(k in text_lower for k in ["bóng rổ", "basketball"]):
                    sport_icon = "🏀"
                elif any(k in text_lower for k in ["tennis", "quần vợt"]):
                    sport_icon = "🎾"

                # Bóc tách Thời gian (Giờ & Ngày)
                time_m = re.search(r'\b(2[0-3]|[0-1]?\d)[:h](\d{2})\b', card_text)
                extracted_time = f"{time_m.group(1).zfill(2)}:{time_m.group(2)}" if time_m else "21:00"

                date_m = re.search(r'\b(\d{1,2})[/.-](\d{1,2})\b', card_text)
                match_date = f"{date_m.group(1).zfill(2)}/{date_m.group(2).zfill(2)}" if date_m else today_str

                # Xác định Dấu chấm trạng thái chính xác theo ảnh mẫu
                status_dot = ""
                if status == 'live':
                    status_dot = "🟢 "
                elif status == 'soon':
                    status_dot = "🟡 "

                # ĐỊNH DẠNG TÊN KÊNH ĐÚNG 100% CHUẨN MẪU TIVIMATE
                # Ví dụ: 🟢 21:00 25/09 ⚽ India vs Panama (Chuối Nhỏ) [FHD] [hls]
                full_title = f"{status_dot}{extracted_time} {match_date} {sport_icon} {teams_title} ({blv_name}) [FHD] [hls]"

                # Lấy link Stream M3U8 theo tên BLV
                blv_slug = to_slug(blv_name)
                stream_url = CASTER_STREAM_MAP.get(
                    blv_slug, 
                    f"https://stm9ee346727718.stream.hdplaylink.com/cctvlive/{blv_slug}hd/playlist.m3u8"
                )

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
                    "status": status,
                    "match_url": match_url
                })

            # Sắp xếp danh sách: Đang live (🟢) -> Sắp đá (🟡) -> Chuẩn bị đá
            parsed_items.sort(key=lambda x: (x['status'] != 'live', x['status'] != 'soon', x['dt']))
            browser.close()

    except Exception as e:
        print(f"[!] Lỗi tiến trình Playwright: {e}")

    # GHI FILE PLAYLIST M3U
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

    print(f"[*] Đã xuất thành công {len(parsed_items)} kênh vào file {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
