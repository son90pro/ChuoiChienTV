import time
import re
from urllib.parse import quote, urlparse
from playwright.sync_api import sync_playwright

WORKER_DOMAIN = "cctv.sonnguyen90pro.workers.dev"
BASE_URL = "https://chuoichientv1.link"

OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Chuối Chiên TV"
DEFAULT_LOGO = "https://raw.githubusercontent.com/iptv-org/iptv/master/logos/sports.png"

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
            page.wait_for_timeout(4000)

            # Cuộn trang để kích hoạt lazy-load nội dung
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(1)

            # Lấy toàn bộ các khối trận đấu hoặc các link bên trong trang chủ
            raw_data = page.evaluate('''() => {
                const results = [];
                // Tìm các thẻ a hoặc các khối match thường dùng trên trang trực tiếp bóng đá
                const elements = document.querySelectorAll('a[href]');
                
                elements.forEach(el => {
                    const href = el.getAttribute('href');
                    if (!href || href === '#' || href.startsWith('javascript') || href.startsWith('tel:')) return;
                    
                    let fullUrl = href.startsWith('http') ? href : window.location.origin + href;
                    
                    // Lọc bỏ các link rác hệ thống thông thường
                    const lowHref = fullUrl.toLowerCase();
                    if (lowHref.includes('login') || lowHref.includes('register') || lowHref.includes('terms') || lowHref.includes('privacy')) return;

                    // Tìm thẻ chứa thông tin trận đấu xung quanh
                    const card = el.closest('div[class*="match"], div[class*="item"], div[class*="card"], article') || el.parentElement || el;
                    const text = card.innerText ? card.innerText.trim() : '';

                    if (text.length > 3) {
                        let logo = '';
                        const img = card.querySelector('img');
                        if (img) {
                            let src = img.getAttribute('src') || img.getAttribute('data-src') || '';
                            if (src && !src.includes('favicon')) {
                                logo = src.startsWith('http') ? src : window.location.origin + src;
                            }
                        }
                        results.push({
                            url: fullUrl,
                            text: text,
                            logo: logo
                        });
                    }
                });
                return results;
            }''')

            unique_matches = {}
            for item in raw_data:
                url = item['url']
                text = item['text']
                
                if url in unique_matches:
                    continue

                # Chuẩn hóa tên trận đấu từ đoạn text thu thập được
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                
                # Bỏ qua các mục quá ngắn hoặc không phải trận đấu
                if len(lines) == 0:
                    continue

                # Lọc lấy các dòng có thông tin đội bóng hoặc giờ giấc
                match_title = " - ".join(lines[:3]) if len(lines) >= 2 else lines[0]
                # Giới hạn độ dài tiêu đề cho gọn gàng trên tivi
                if len(match_title) > 80:
                    match_title = match_title[:80] + "..."

                unique_matches[url] = {
                    "title": match_title.replace('\n', ' '),
                    "logo": item['logo'],
                    "url": url
                }

            match_list = list(unique_matches.values())
            page.close()

            print(f"[*] Tìm thấy {len(match_list)} mục. Đang quét link stream m3u8...")
            for idx, match in enumerate(match_list):
                print(f"[{idx+1}/{len(match_list)}] Đang xử lý: {match['title']}")
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

    print(f"[*] Đã xuất file {OUTPUT_FILE} thành công!")

if __name__ == "__main__":
    run_scraper()
    
