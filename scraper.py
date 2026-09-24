import time
import re
from urllib.parse import quote
from playwright.sync_api import sync_playwright

WORKER_DOMAIN = "cctv.sonnguyen90pro.workers.dev"
BASE_URL = "https://phalang.tv"

OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Phà Lăng TV"

EXCLUDE_KEYWORDS = [
    'lịch thi đấu', 'kết quả', 'tin tức', 'bảng xếp hạng', 'soi kèo',
    'nhà cái', 'đăng ký', 'đăng nhập', 'khuyến mãi', 'liên hệ', 'giới thiệu',
    'chính sách', 'hướng dẫn', 'tải app', 'privacy', 'terms'
]

NOISE_EXACT = {
    'xem ngay', 'xem trực tiếp', 'trực tiếp', 'sắp diễn ra', 'đang diễn ra',
    'hiệp 1', 'hiệp 2', 'hết giờ', 'ft', 'ht', 'live', 'hot', 'chi tiết', 'xem',
    'vs', 'v/s', '-', '–', '[geo]', 'geo'
}

LEAGUE_KEYWORDS = [
    'friendly', 'cup', 'league', 'championship', 'fifa', 'waff', 'asean',
    'asian', 'afc', 'uefa', 'premier', 'la liga', 'serie', 'bundesliga', 'v-league', 'international'
]

def clean_match_title(item):
    raw_text = item.get('text', '')
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    
    time_str = ""
    filtered_lines = []
    
    for line in lines:
        l_low = line.lower()
        
        # Bỏ các từ trạng thái rác
        if l_low in NOISE_EXACT:
            continue

        # Trích xuất thời gian (VD: 17:05 24/09 hoặc 17:05)
        time_match = re.search(r'\b\d{1,2}:\d{2}(\s+\d{1,2}/\d{1,2})?\b', line)
        if time_match and not time_str:
            time_str = time_match.group(0)
            continue

        # Lọc bỏ tên giải đấu nếu nằm riêng 1 dòng
        if any(lg in l_low for lg in LEAGUE_KEYWORDS) and not re.search(r'\b(vs|v/s)\b', l_low):
            continue

        filtered_lines.append(line)

    teams_str = ""
    blv_str = ""

    # Trường hợp 1: Có dòng chứa sẵn chữ "vs" (VD: Japan vs Uruguay)
    vs_line_idx = -1
    for idx, line in enumerate(filtered_lines):
        if re.search(r'\b(vs|v/s)\b', line, re.IGNORECASE):
            vs_line_idx = idx
            break

    if vs_line_idx != -1:
        teams_str = filtered_lines[vs_line_idx]
        remaining = [l for i, l in enumerate(filtered_lines) if i != vs_line_idx]
        if remaining:
            blv_str = remaining[-1]
    else:
        # Trường hợp 2: Tên Đội 1, Tên Đội 2, Tên BLV nằm ở các dòng riêng biệt
        if len(filtered_lines) >= 3:
            teams_str = f"{filtered_lines[0]} vs {filtered_lines[1]}"
            blv_str = filtered_lines[2]  # Dòng thứ 3 chính là tên BLV!
        elif len(filtered_lines) == 2:
            teams_str = f"{filtered_lines[0]} vs {filtered_lines[1]}"
        elif len(filtered_lines) == 1:
            teams_str = filtered_lines[0]
        else:
            teams_str = "Trận đấu Phà Lăng TV"

    # Làm sạch tên đội bóng
    teams_str = re.sub(r'\s+', ' ', teams_str).strip()
    teams_str = re.sub(r'\s+(VS|vs|v/s)\s+', ' vs ', teams_str)

    # Định dạng tên BLV thành CHỮ HOA trong ngoặc đơn: (LÝ LA LÀNG)
    formatted_blv = ""
    if blv_str:
        clean_blv = re.sub(r'^(BLV|Caster|Bình luận viên|BLV:)\s*[:\-]?\s*', '', blv_str, flags=re.IGNORECASE).strip()
        clean_blv = clean_blv.strip('()[]')
        if clean_blv:
            formatted_blv = f"({clean_blv.upper()})"

    # Ghép chuẩn định dạng: 17:05 24/09 ⚽ Japan vs Uruguay (LÝ LA LÀNG) [geo]
    parts = []
    if time_str:
        parts.append(time_str)
    
    parts.append("⚽")
    parts.append(teams_str)
    
    if formatted_blv:
        parts.append(formatted_blv)
        
    parts.append("[geo]")

    return " ".join(parts)

def is_valid_match_url(href, text):
    low_href = href.lower()
    low_text = text.lower()

    for kw in EXCLUDE_KEYWORDS:
        if kw in low_text or kw.replace(' ', '-') in low_href:
            return False

    if low_href.strip() in [BASE_URL.lower(), BASE_URL.lower() + "/", "#", "javascript:void(0)"]:
        return False

    if len(href) <= len(BASE_URL) + 2:
        return False

    return True

def get_m3u8_for_match(context, match_url):
    page = context.new_page()
    page.route("**/*.{png,jpg,jpeg,svg,css,woff,woff2}", lambda route: route.abort())
    
    m3u8_found = []

    def handle_request(request):
        url = request.url
        if ".m3u8" in url and "blob:" not in url:
            m3u8_found.append(url)

    page.on("request", handle_request)

    try:
        page.goto(match_url, timeout=15000, wait_until="domcontentloaded")
        for _ in range(10):
            if m3u8_found:
                break
            time.sleep(0.5)
    except Exception:
        pass
    finally:
        page.close()

    return m3u8_found[0] if m3u8_found else None

def run_scraper():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )

        final_matches = []
        page = context.new_page()

        try:
            print(f"[*] Đang tải trang Phà Lăng TV: {BASE_URL}")
            page.goto(BASE_URL, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)

            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            time.sleep(2)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(1)

            # Thu thập toàn bộ văn bản trong khung trận đấu bằng cách duyệt ngược DOM
            raw_matches = page.evaluate('''() => {
                const matches = [];
                const links = document.querySelectorAll('a[href]');

                links.forEach(el => {
                    const href = el.getAttribute('href');
                    if (!href || href === '#' || href.startsWith('javascript')) return;

                    const fullUrl = href.startsWith('http') ? href : window.location.origin + href;
                    if (fullUrl === window.location.origin + '/' || fullUrl === window.location.origin) return;

                    // Duyệt ngược lên 3-4 cấp để bao trọn khung chứa trận đấu
                    let box = el;
                    for (let i = 0; i < 4; i++) {
                        if (box.parentElement && box.parentElement.tagName !== 'BODY') {
                            if (box.parentElement.querySelectorAll('a[href]').length > 4) {
                                break;
                            }
                            box = box.parentElement;
                        }
                    }

                    const text = box.innerText ? box.innerText.trim() : '';

                    let logo = '';
                    const img = box.querySelector('img');
                    if (img) {
                        let src = img.getAttribute('src') || img.getAttribute('data-src') || '';
                        if (src && !src.includes('favicon')) {
                            logo = src.startsWith('http') ? src : window.location.origin + src;
                        }
                    }

                    if (text.length > 5) {
                        matches.push({
                            url: fullUrl,
                            text: text,
                            logo: logo
                        });
                    }
                });
                return matches;
            }''')

            unique_matches = {}
            for item in raw_matches:
                url = item['url']

                if url in unique_matches:
                    continue

                if not is_valid_match_url(url, item['text']):
                    continue

                formatted_title = clean_match_title(item)

                unique_matches[url] = {
                    "title": formatted_title,
                    "logo": item['logo'],
                    "url": url
                }

            match_list = list(unique_matches.values())
            page.close()

            print(f"[*] Tìm thấy {len(match_list)} trận đấu trên Phà Lăng TV. Đang trích xuất link stream...")
            for idx, match in enumerate(match_list):
                print(f"[{idx+1}/{len(match_list)}] Lấy stream: {match['title']}")
                m3u8_url = get_m3u8_for_match(context, match['url'])
                match['m3u8_url'] = m3u8_url

            final_matches = match_list

        except Exception as e:
            print(f"[!] Lỗi: {e}")
            page.close()

        browser.close()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")

        for item in final_matches:
            logo_attr = f'tvg-logo="{item["logo"]}"' if item["logo"] else ''
            ref_url = BASE_URL

            if item.get('m3u8_url'):
                encoded_m3u8 = quote(item['m3u8_url'], safe='')
                encoded_ref = quote(ref_url, safe='')
                stream_url = f"https://{WORKER_DOMAIN}/proxy?url={encoded_m3u8}&referer={encoded_ref}"
            else:
                stream_url = f"https://{WORKER_DOMAIN}/proxy?url={quote(item['url'], safe='')}"
            
            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}",{item["title"]}\n')
            f.write(f'{stream_url}\n\n')

    print(f"[*] Hoàn tất! Đã xuất {len(final_matches)} trận vào {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
