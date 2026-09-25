import time
import re
import json
import unicodedata
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

# Danh sách các tên miền gương của Chuối Chiên TV (Tự động chuyển nếu bị chặn)
DOMAINS = [
    "https://chuoichientv.net",
    "https://live07.chuoichientv.me",
    "https://chuoichien.tv",
    "https://chuoichien.live",
    "https://live.chuoichien.tv"
]

REFERER_URL = "https://live.chuoichien.tv/"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Chuối Chiên TV"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Bảng ánh xạ Server Stream chuẩn từng BLV
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
    if not name:
        return ""
    name = re.sub(r'^\d+[\.\s]*', '', name)
    name = re.sub(r'\s*(FHD|HLS|HD|Live|Trực tiếp)\s*', '', name, flags=re.I)
    return name.strip()

def build_emergency_channels():
    """Tạo danh sách kênh dự phòng khi trang web bị sự cố/chặn IP"""
    vn_tz = timezone(timedelta(hours=7))
    now_str = datetime.now(vn_tz).strftime("%H:%M %d/%m")
    items = []
    for blv in KNOWN_BLVS:
        slug = to_slug(blv)
        stream_url = CASTER_STREAM_MAP.get(slug, f"https://stm9ee346727718.stream.hdplaylink.com/cctvlive/{slug}hd/playlist.m3u8")
        title = f"🟢 {now_str} ⚽ Kênh Trực Tiếp ({blv}) [FHD] [hls]"
        items.append({
            "title": title,
            "logo": DEFAULT_LOGO,
            "stream_url": stream_url,
            "match_url": f"emergency-{slug}"
        })
    return items

def run_scraper():
    vn_tz = timezone(timedelta(hours=7))
    today_str = datetime.now(vn_tz).strftime("%d/%m")
    raw_matches = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage"
                ]
            )
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 720},
                timezone_id="Asia/Ho_Chi_Minh",
                locale="vi-VN",
                extra_http_headers={
                    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"Windows"'
                }
            )

            # Thử từng tên miền cho đến khi lấy được dữ liệu
            for base_url in DOMAINS:
                print(f"[*] Thử kết nối tới tên miền: {base_url}")
                try:
                    page = context.new_page()
                    
                    # Bắt các gói tin API nếu trang web dùng React/Vue
                    api_data = []
                    def handle_response(response):
                        try:
                            if "api" in response.url.lower() and response.status == 200:
                                ct = response.headers.get("content-type", "")
                                if "json" in ct:
                                    json_body = response.json()
                                    if isinstance(json_body, (dict, list)):
                                        api_data.append(json_body)
                        except Exception:
                            pass
                    
                    page.on("response", handle_response)

                    page.goto(base_url, timeout=30000, wait_until="domcontentloaded")
                    time.sleep(3)

                    # Cuộn trang để kích hoạt lazy loading
                    for _ in range(3):
                        page.evaluate("window.scrollBy(0, 800)")
                        time.sleep(0.4)

                    # 1. Trích xuất từ DOM HTML
                    extracted = page.evaluate('''() => {
                        const results = [];
                        const seenUrls = new Set();
                        
                        // Lấy tất cả thẻ <a> hoặc phần tử có link
                        const links = document.querySelectorAll('a[href]');
                        links.forEach(a => {
                            const href = a.getAttribute('href');
                            if (!href || href === '#' || href.startsWith('javascript')) return;
                            
                            const fullUrl = href.startsWith('http') ? href : window.location.origin + href;
                            if (seenUrls.has(fullUrl)) return;

                            // Tìm khung chứa card trận đấu
                            let container = a;
                            let parent = a.parentElement;
                            while (parent && parent.tagName !== 'BODY') {
                                if (parent.innerText && parent.innerText.length > 20 && parent.innerText.length < 500) {
                                    container = parent;
                                    break;
                                }
                                parent = parent.parentElement;
                            }

                            const text = container.innerText || a.innerText || '';
                            if (!text || text.length < 5) return;

                            // Kiểm tra xem card có chứa thông tin trận đấu không (có chữ vs, hoặc thời gian)
                            if (text.toLowerCase().includes('vs') || /\\d{1,2}[:h]\\d{2}/.test(text)) {
                                seenUrls.add(fullUrl);

                                // Lấy logo
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

                                // Lấy tên 2 đội nếu có class riêng
                                const teamEls = container.querySelectorAll('.team-name, .home-name, .away-name, [class*="team"], [class*="club"]');
                                let dom_t1 = '', dom_t2 = '';
                                if (teamEls.length >= 2) {
                                    dom_t1 = teamEls[0].innerText.trim();
                                    dom_t2 = teamEls[1].innerText.trim();
                                }

                                const htmlAll = container.innerHTML.toLowerCase();
                                let status = 'upcoming';
                                if (htmlAll.includes('live') || text.includes('Đang diễn ra') || text.includes('Hiệp 1') || text.includes('Hiệp 2')) {
                                    status = 'live';
                                } else if (text.includes('Sắp diễn ra') || text.includes('Chuẩn bị')) {
                                    status = 'soon';
                                }

                                results.push({
                                    url: fullUrl,
                                    rawText: text,
                                    team1: dom_t1,
                                    team2: dom_t2,
                                    logo: logoUrl,
                                    status: status
                                });
                            }
                        });
                        return results;
                    }''')

                    page.close()

                    if extracted and len(extracted) > 0:
                        raw_matches = extracted
                        print(f"[+] Lấy thành công {len(raw_matches)} trận từ tên miền: {base_url}")
                        break
                    else:
                        print(f"[-] Tên miền {base_url} không trả về kết quả nào.")

                except Exception as err:
                    print(f"[!] Lỗi khi truy cập {base_url}: {err}")

            browser.close()

    except Exception as e:
        print(f"[!] Lỗi hệ thống Playwright: {e}")

    parsed_items = []

    # Xử lý kết quả cào được
    if raw_matches:
        for item in raw_matches:
            match_url = item['url']
            card_text = item['rawText']
            card_logo = item['logo'] if item['logo'] else DEFAULT_LOGO
            status = item['status']

            # 1. Bóc tách tên BLV
            blv_name = "Chuối Chiên"
            for b in KNOWN_BLVS:
                if b.lower() in card_text.lower() or to_slug(b) in match_url.lower():
                    blv_name = b
                    break

            # 2. Bóc tách tên 2 đội bóng chuẩn
            t1 = clean_team_name(item['team1'])
            t2 = clean_team_name(item['team2'])
            
            if not t1 or not t2:
                match_vs = re.search(r'([A-Za-zÀ-ỹ0-9\s\.]{2,25})\s+vs\s+([A-Za-zÀ-ỹ0-9\s\.]{2,25})', card_text, re.I)
                if match_vs:
                    t1 = clean_team_name(match_vs.group(1))
                    t2 = clean_team_name(match_vs.group(2))

            teams_title = f"{t1} vs {t2}" if (t1 and t2) else "Trận đấu Trực Tiếp"

            # 3. Nhận diện icon môn thể thao
            sport_icon = "⚽"
            text_lower = card_text.lower()
            if any(k in text_lower for k in ["bóng chuyền", "volleyball"]):
                sport_icon = "🏐"
            elif any(k in text_lower for k in ["bóng rổ", "basketball"]):
                sport_icon = "🏀"
            elif any(k in text_lower for k in ["tennis", "quần vợt"]):
                sport_icon = "🎾"

            # 4. Bóc tách Thời gian
            time_m = re.search(r'\b(2[0-3]|[0-1]?\d)[:h](\d{2})\b', card_text)
            extracted_time = f"{time_m.group(1).zfill(2)}:{time_m.group(2)}" if time_m else "21:00"

            date_m = re.search(r'\b(\d{1,2})[/.-](\d{1,2})\b', card_text)
            match_date = f"{date_m.group(1).zfill(2)}/{date_m.group(2).zfill(2)}" if date_m else today_str

            # 5. Dấu chấm trạng thái TiviMate chuẩn mẫu 1824.jpg
            status_dot = ""
            if status == 'live':
                status_dot = "🟢 "
            elif status == 'soon':
                status_dot = "🟡 "

            # Tiêu đề kênh chuẩn: 🟢 21:00 25/09 ⚽ India vs Panama (Chuối Nhỏ) [FHD] [hls]
            full_title = f"{status_dot}{extracted_time} {match_date} {sport_icon} {teams_title} ({blv_name}) [FHD] [hls]"

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

        parsed_items.sort(key=lambda x: (x['status'] != 'live', x['status'] != 'soon', x['dt']))

    # CHẾ ĐỘ DỰ PHÒNG KHẨN CẤP: Nếu cào không được trận nào, xuất danh sách kênh BLV mặc định
    if not parsed_items:
        print("[!] Không tìm thấy trận đấu trực tiếp. Kích hoạt danh sách kênh dự phòng khẩn cấp!")
        parsed_items = build_emergency_channels()

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
    
