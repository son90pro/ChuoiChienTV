import time
import re
from urllib.parse import quote
from playwright.sync_api import sync_playwright

# Tên miền Cloudflare Worker mới của anh Sơn
WORKER_DOMAIN = "cctv.sonnguyen90pro.workers.dev"

BASE_URL = "https://chuoichientv.com"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Chuối Chiên TV"

FILTER_KEYWORDS = [
    "cup", "cúp", "league", "championship", "v-league", "premier", 
    "champions", "euro", "copa", "afc", "fifa", "uefa", "serie", "liga"
]

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
        for _ in range(8):
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
        page = context.new_page()

        final_matches = []
        try:
            print(f"[*] Đang tải trang chủ: {BASE_URL}")
            page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            # Bóc tách danh sách trận đấu từ Chuối Chiên TV
            raw_matches = page.evaluate('''() => {
                const matches = [];
                const cards = Array.from(document.querySelectorAll('a[href*="/truc-tiep/"], a[href*="/match/"], a[href*="/xem-bong-da/"], .match-item, .card-match'));

                cards.forEach(card => {
                    const linkEl = card.tagName === 'A' ? card : card.querySelector('a');
                    if (!linkEl) return;
                    
                    const href = linkEl.getAttribute('href');
                    if (!href) return;

                    let logo = '';
                    const img = card.querySelector('img');
                    if (img) {
                        logo = img.getAttribute('src') || img.getAttribute('data-src') || '';
                        if (logo && !logo.startsWith('http')) logo = window.location.origin + logo;
                    }

                    matches.push({
                        url: href.startsWith('http') ? href : window.location.origin + href,
                        text: card.innerText || '',
                        logo: logo
                    });
                });

                return matches;
            }''')

            unique_matches = {}
            for item in raw_matches:
                url = item['url']
                text = item['text']
                if not text or url in unique_matches:
                    continue

                # Lấy thời gian
                time_match = re.search(r'(\d{1,2}:\d{2})', text)
                date_match = re.search(r'(\d{1,2}/\d{1,2})', text)
                m_time = time_match.group(1) if time_match else "LIVE"
                m_date = date_match.group(1) if date_match else ""
                time_str = f"{m_time} {m_date}".strip()

                # Lấy tên BLV (Ví dụ: Chuối Chao, Chuối Kem, Chuối Tây, Chuối To...)
                blv_match = re.search(r'\((Chuối\s+[A-Za-zÀ-ỹ0-9\s]+)\)', text, re.IGNORECASE)
                blv_str = f" ({blv_match.group(1)})" if blv_match else ""

                # Làm sạch tiêu đề trận đấu
                lines = [l.strip() for l in text.split('\n') if l.strip() and not re.search(r'\d{1,2}:\d{2}', l)]
                title_clean = " ".join(lines[:2]) if lines else "Trận đấu Trực Tiếp"
                title_clean = re.sub(r'\[hls\]|\[flv\]', '', title_clean, flags=re.IGNORECASE).strip()

                full_title = f"{time_str} ⚽ {title_clean}{blv_str}"

                unique_matches[url] = {
                    "title": full_title,
                    "logo": item['logo'],
                    "url": url
                }

            match_list = list(unique_matches.values())
            print(f"[*] Tìm thấy {len(match_list)} trận đấu từ Chuối Chiên TV.")

            page.close()

            # Quét tìm luồng stream m3u8
            for idx, match in enumerate(match_list):
                print(f"[{idx+1}/{len(match_list)}] Tìm stream cho: {match['title']}")
                m3u8_url = get_m3u8_for_match(context, match['url'])
                match['m3u8_url'] = m3u8_url

            final_matches = match_list

        except Exception as e:
            print(f"Lỗi khi cào dữ liệu: {e}")
        finally:
            browser.close()

    # Xuất dữ liệu ra file playlist.m3u
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")

        for item in final_matches:
            logo_attr = f'tvg-logo="{item["logo"]}"' if item["logo"] else ''
            
            if item.get('m3u8_url'):
                encoded_m3u8 = quote(item['m3u8_url'], safe='')
                encoded_ref = quote(BASE_URL + '/', safe='')
                # Truyền tham số referer qua Cloudflare Worker để bypass chặn
                stream_url = f"https://{WORKER_DOMAIN}/proxy?url={encoded_m3u8}&referer={encoded_ref}"
            else:
                stream_url = f"https://{WORKER_DOMAIN}/live?url={quote(item['url'], safe='')}"
            
            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}",{item["title"]}\n')
            f.write(f'{stream_url}\n\n')

    print(f"[*] Đã hoàn tất xuất file {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
