import time
import re
from urllib.parse import quote
from playwright.sync_api import sync_playwright

WORKER_DOMAIN = "cctv.sonnguyen90pro.workers.dev"
BASE_URL = "https://live07.chuoichientv.me"

OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Chuối Chiên TV"
DEFAULT_LOGO = "https://raw.githubusercontent.com/iptv-org/iptv/master/logos/sports.png"

# Các từ khóa của menu hệ thống, kết quả, lịch thi đấu cần loại bỏ tuyệt đối
EXCLUDE_KEYWORDS = [
    'lịch thi đấu', 'kết quả', 'tin thể thao', 'top nhà cái', 'đăng nhập', 
    'trang chủ', 'tải app', 'khuyến mãi', 'nạp tiền', 'rút tiền', 'bảng xếp hạng',
    'trang chủ chính thức', 'landing'
]

def is_real_match(text, href):
    low_text = text.lower()
    low_href = href.lower()

    # Kiểm tra nếu dính từ khóa menu hệ thống hoặc rác
    for kw in EXCLUDE_KEYWORDS:
        if kw in low_text:
            return False

    # Loại bỏ link trỏ về trang chủ hoặc neo rỗng
    if low_href.strip() in [BASE_URL, BASE_URL + "/", "#", "javascript:void(0)"]:
        return False

    # Trận đấu thực tế phải có từ khóa hiệp đấu, thời gian trực tiếp, dấu vs, hoặc tên giải đấu/đội bóng
    has_match_sign = (
        'hiệp' in low_text or 'vs' in low_text or 'live' in low_text or 
        'trực tiếp' in low_text or ' - ' in text or 
        bool(re.search(r'\d{1,2}:\d{2}', text)) or
        bool(re.search(r'(vđqg|premier|la liga|serie a|bundesliga|champions|cup|cúp|anh|tây ban nha|ý|đức|pháp|việt nam)', low_text))
    )

    return has_match_sign

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
        page.goto(match_url, timeout=12000, wait_until="domcontentloaded")
        for _ in range(6):
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
            print(f"[*] Đang tải trang live: {BASE_URL}")
            page.goto(BASE_URL, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)

            # Cuộn trang để hiển thị đầy đủ danh sách trận đấu động
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(3)
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

                    # Lấy khung chứa thông tin trận đấu
                    const card = el.closest('div[class*="match"], div[class*="item"], div[class*="game"], div[class*="card"], article') || el.parentElement || el;
                    const text = card.innerText ? card.innerText.trim() : '';

                    if (text.length > 5) {
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
                text = item['text']
                if url in unique_matches:
                    continue

                if not is_real_match(text, url):
                    continue

                lines = [l.strip() for l in text.split('\n') if l.strip()]
                if not lines:
                    continue

                match_title = " - ".join(lines[:2]) if len(lines) >= 2 else lines[0]
                if len(match_title) > 85:
                    match_title = match_title[:85] + "..."

                unique_matches[url] = {
                    "title": match_title.replace('\n', ' '),
                    "logo": item['logo'],
                    "url": url
                }

            match_list = list(unique_matches.values())
            page.close()

            print(f"[*] Lọc chính xác {len(match_list)} trận đấu thực tế. Đang lấy link m3u8...")
            for idx, match in enumerate(match_list):
                print(f"[{idx+1}/{len(match_list)}] Lấy link: {match['title']}")
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

    print(f"[*] Xuất file {OUTPUT_FILE} thành công!")

if __name__ == "__main__":
    run_scraper()
    
