import time
import re
from urllib.parse import quote
from playwright.sync_api import sync_playwright

WORKER_DOMAIN = "cctv.sonnguyen90pro.workers.dev"
BASE_URL = "https://phalang.tv"

OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Phà Lăng TV"

# Từ khóa menu/trang tĩnh cần lọc bỏ
EXCLUDE_KEYWORDS = [
    'lịch thi đấu', 'kết quả', 'tin tức', 'bảng xếp hạng', 'soi kèo',
    'nhà cái', 'đăng ký', 'đăng nhập', 'khuyến mãi', 'liên hệ', 'giới thiệu',
    'chính sách', 'hướng dẫn', 'tải app', 'privacy', 'terms'
]

# Từ khóa trạng thái rác cần loại khỏi tiêu đề
STATUS_NOISE = {
    'xem ngay', 'xem trực tiếp', 'trực tiếp', 'sắp diễn ra', 'đang diễn ra', 
    'hiệp 1', 'hiệp 2', 'hết giờ', 'ft', 'ht', 'live', 'hot', 'chi tiết', 'xem'
}

def clean_match_title(raw_text):
    """ Bóc tách và định dạng lại tên trận đấu: [Thời gian] Đội A vs Đội B (BLV) """
    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    
    time_str = ""
    blv_str = ""
    other_lines = []
    
    for line in lines:
        l_low = line.lower()
        
        # Bỏ qua dòng trạng thái rác
        if l_low in STATUS_NOISE:
            continue
        
        # Nhận diện BLV
        if 'blv' in l_low or 'bình luận' in l_low:
            blv_str = line
        # Nhận diện thời gian (VD: 17:05 hoặc 17:05 24/09)
        elif re.search(r'\b\d{1,2}:\d{2}\b', line):
            cleaned_time = re.sub(r'-\s*(Sắp diễn ra|Đang diễn ra|Hết giờ|Trực tiếp).*', '', line, flags=re.IGNORECASE).strip()
            time_str = cleaned_time
        else:
            other_lines.append(line)
            
    # Ghép các phần lại thành tiêu đề chuẩn
    title_components = []
    
    if time_str:
        title_components.append(f"[{time_str}]")
        
    if other_lines:
        joined_teams = " ".join(other_lines)
        joined_teams = re.sub(r'\s+', ' ', joined_teams)
        title_components.append(joined_teams)
        
    if blv_str:
        title_components.append(f"({blv_str})")
        
    if not title_components:
        return "Trận đấu Phà Lăng TV"
        
    final_title = " ".join(title_components)
    if len(final_title) > 95:
        final_title = final_title[:95] + "..."
    return final_title

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

            raw_matches = page.evaluate('''() => {
                const matches = [];
                const links = document.querySelectorAll('a[href]');

                links.forEach(el => {
                    const href = el.getAttribute('href');
                    if (!href || href === '#' || href.startsWith('javascript')) return;

                    const fullUrl = href.startsWith('http') ? href : window.location.origin + href;
                    
                    if (fullUrl === window.location.origin + '/' || fullUrl === window.location.origin) return;

                    const card = el.closest('.match-item, .item, .card, .game-item, article, [class*="match"], [class*="live"]') || el.parentElement || el;
                    const text = card.innerText ? card.innerText.trim() : el.innerText.trim();

                    if (text.length > 3) {
                        let logo = '';
                        const img = card.querySelector('img');
                        if (img) {
                            let src = img.getAttribute('src') || img.getAttribute('data-src') || '';
                            if (src && !src.includes('favicon')) {
                                logo = src.startsWith('http') ? src : window.location.origin + src;
                            }
                        }

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
                raw_text = item['text']

                if url in unique_matches:
                    continue

                if not is_valid_match_url(url, raw_text):
                    continue

                formatted_title = clean_match_title(raw_text)

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
    
