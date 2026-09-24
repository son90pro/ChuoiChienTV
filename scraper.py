import time
import re
from urllib.parse import quote
from playwright.sync_api import sync_playwright

WORKER_DOMAIN = "cctv.sonnguyen90pro.workers.dev"
BASE_URL = "https://chuoichientv1.link"

OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Chuối Chiên TV"
DEFAULT_LOGO = "https://raw.githubusercontent.com/iptv-org/iptv/master/logos/sports.png"

# Các từ khóa nhận diện link hệ thống, landing, quảng cáo cần loại bỏ tuyệt đối
IGNORE_PATTERNS = [
    'landing', 'trang chủ', 'website chính thức', 'lịch •', 'đăng ký', 
    'khuyến mãi', 'nạp tiền', 'rút tiền', 'uk88', 'vin88', 'debet', 'sky88'
]

def is_match_card(text, href):
    low_text = text.lower()
    low_href = href.lower()

    # Loại bỏ nếu chứa từ khóa rác hoặc landing page
    for pat in IGNORE_PATTERNS:
        if pat in low_text or pat in low_href:
            return False

    # Loại bỏ link trỏ về chính trang chủ
    if low_href.strip() in [BASE_URL, BASE_URL + "/", "#", "javascript:void(0)"]:
        return False

    # Tiêu chuẩn của một trận đấu thường có tên đội, ký hiệu đấu hoặc thời gian trực tiếp
    has_match_indicator = ('vs' in low_text or ' - ' in text or 'live' in low_text or 
                           'trực tiếp' in low_text or bool(re.search(r'\d{1,2}:\d{2}', text)))
    
    return has_match_indicator

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
            print(f"[*] Đang tải trang chủ: {BASE_URL}")
            page.goto(BASE_URL, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)

            # Cuộn trang tối đa để kích hoạt toàn bộ danh sách trận đấu render đầy đủ
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(3)
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(2)

            # Trích xuất toàn bộ liên kết và các thẻ card trận đấu thực tế
            raw_data = page.evaluate('''() => {
                const results = [];
                const links = document.querySelectorAll('a[href]');
                
                links.forEach(el => {
                    const href = el.getAttribute('href');
                    if (!href) return;
                    
                    let fullUrl = href.startsWith('http') ? href : window.location.origin + href;
                    
                    // Tìm phần tử bao chứa thông tin trận đấu gần nhất
                    const card = el.closest('div[class*="match"], div[class*="game"], div[class*="item"], div[class*="live"], article') || el.parentElement || el;
                    const text = card.innerText ? card.innerText.trim() : '';

                    let logo = '';
                    const img = card.querySelector('img');
                    if (img) {
                        let src = img.getAttribute('src') || img.getAttribute('data-src') || '';
                        if (src && !src.includes('favicon') && !src.includes('logo-site')) {
                            logo = src.startsWith('http') ? src : window.location.origin + src;
                        }
                    }

                    results.push({
                        url: fullUrl,
                        text: text,
                        logo: logo
                    });
                });
                return results;
            }''')

            unique_matches = {}
            for item in raw_data:
                url = item['url']
                text = item['text']
                
                if url in unique_matches:
                    continue

                if not is_match_card(text, url):
                    continue

                # Làm sạch và định dạng tên tiêu đề trận đấu
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                match_title = " - ".join(lines[:3]) if len(lines) >= 2 else lines[0]
                if len(match_title) > 90:
                    match_title = match_title[:90] + "..."

                unique_matches[url] = {
                    "title": match_title.replace('\n', ' '),
                    "logo": item['logo'],
                    "url": url
                }

            match_list = list(unique_matches.values())
            page.close()

            print(f"[*] Đã lọc thành công {len(match_list)} trận đấu. Đang tiến hành lấy link m3u8...")
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
            ref_url = "https://chuoichientv1.link"

            if item.get('m3u8_url'):
                encoded_m3u8 = quote(item['m3u8_url'], safe='')
                encoded_ref = quote(ref_url + '/', safe='')
                stream_url = f"https://{WORKER_DOMAIN}/proxy?url={encoded_m3u8}&referer={encoded_ref}"
            else:
                stream_url = f"https://{WORKER_DOMAIN}/proxy?url={quote(item['url'], safe='')}"
            
            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}",{item["title"]}\n')
            f.write(f'{stream_url}\n\n')

    print(f"[*] Xuất file {OUTPUT_FILE} hoàn tất!")

if __name__ == "__main__":
    run_scraper()
    
