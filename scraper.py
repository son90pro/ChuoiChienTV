import time
import re
from urllib.parse import quote
from playwright.sync_api import sync_playwright

BASE_URL = "https://phalang.live"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Phá Làng TV"
REFERRER_HEADER = "https://phalang.live/"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

def run_scraper():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 720},
            timezone_id="Asia/Ho_Chi_Minh",
            locale="vi-VN"
        )
        page = context.new_page()

        parsed_channels = []

        try:
            print(f"[*] Đang tải trang chủ: {BASE_URL}")
            page.goto(BASE_URL, timeout=40000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)

            # Lấy danh sách các thẻ trận đấu trên trang chủ
            matches_data = page.evaluate('''() => {
                const results = [];
                const cards = document.querySelectorAll('a[href*="/truc-tiep/"], a[href*="/match/"], a[href*="/live/"]');
                const seenUrls = new Set();

                cards.forEach(card => {
                    const href = card.getAttribute('href');
                    if (!href) return;
                    const fullUrl = href.startsWith('http') ? href : window.location.origin + href;
                    if (seenUrls.has(fullUrl)) return;
                    seenUrls.add(fullUrl);

                    // Lấy logo
                    const img = card.querySelector('img');
                    const logo = img ? (img.src || img.getAttribute('data-src') || '') : '';

                    // Lấy toàn bộ text trên card
                    const text = card.innerText || card.parentElement.innerText || '';

                    results.push({
                        url: fullUrl,
                        logo: logo,
                        rawText: text
                    });
                });
                return results;
            }''')

            print(f"[*] Tìm thấy {len(matches_data)} trận đấu. Bắt đầu bóc tách luồng stream...")

            for idx, item in enumerate(matches_data):
                match_url = item['url']
                logo = item['logo']
                text = item['rawText']

                # Mở trang chi tiết từng trận để chộp luồng .m3u8
                detail_page = context.new_page()
                # Chặn hình ảnh/css không cần thiết để tăng tốc
                detail_page.route("**/*.{png,jpg,jpeg,svg,css,woff,woff2,gif}", lambda route: route.abort())

                m3u8_list = []
                def handle_request(req):
                    url = req.url
                    if ".m3u8" in url and "blob:" not in url:
                        if url not in m3u8_list:
                            m3u8_list.append(url)

                detail_page.on("request", handle_request)

                try:
                    detail_page.goto(match_url, timeout=15000, wait_until="domcontentloaded")
                    time.sleep(2.5)
                except Exception:
                    pass
                finally:
                    detail_page.close()

                if not m3u8_list:
                    continue

                # Phân tích thông tin hiển thị (Thời gian, Trạng thái, BLV)
                # Đèn trạng thái
                status_icon = ""
                if "trực tiếp" in text.lower() or "live" in text.lower() or "đang diễn ra" in text.lower():
                    status_icon = "🟢 "
                elif "sắp diễn ra" in text.lower():
                    status_icon = "🟡 "

                # Thời gian & Ngày
                time_match = re.search(r'(\d{1,2}[:h]\d{2})\s*(\d{1,2}/\d{1,2})?', text)
                time_str = ""
                if time_match:
                    t_val = time_match.group(1).replace('h', ':')
                    d_val = f" {time_match.group(2)}" if time_match.group(2) else ""
                    time_str = f"{t_val}{d_val} "

                # Tên BLV
                blv_match = re.search(r'\(([^)]*BLV[^)]*)\)|\b((?:LÝ|BLV|GA)\s+[A-Za-zÀ-ỹ0-9\s]+)', text, re.I)
                blv_str = f" ({blv_match.group(1) or blv_match.group(2)})" if blv_match else ""

                # Trích xuất tên 2 đội từ URL
                teams_title = "Trận đấu Trực Tiếp"
                slug_match = re.search(r'/(?:truc-tiep|match|live)/([^/?#]+)', match_url)
                if slug_match:
                    parts = slug_match.group(1).split('-vs-')
                    if len(parts) == 2:
                        t1 = re.sub(r'^(?:blv-)?ga-(?:sieu-)?[a-z0-9]+-', '', parts[0], flags=re.I).replace('-', ' ').title()
                        t2 = re.sub(r'-(?:luc|ngay|318|y39).*$', '', parts[1], flags=re.I).replace('-', ' ').title()
                        teams_title = f"{t1} vs {t2}"

                base_title = f"{status_icon}{time_str}⚽ {teams_title}{blv_str}".strip()

                # Phân loại luồng stream thu thập được (HD1, HD2, Nhà đài)
                for m3u8_url in m3u8_list:
                    sub_tag = ""
                    if "pull1.digitalcdn.net" in m3u8_url:
                        sub_tag = " (HD2)"
                    elif "lilive" in m3u8_url or "eu.cc" in m3u8_url:
                        sub_tag = " (Nhà đài)"
                    elif "pull.digitalcdn.net" in m3u8_url and len(m3u8_list) > 1:
                        sub_tag = ""

                    geo_tag = " [geo]" if "digitalcdn" in m3u8_url else ""
                    final_title = f"{base_title}{sub_tag}{geo_tag}"

                    parsed_channels.append({
                        "title": final_title,
                        "logo": logo,
                        "url": m3u8_url
                    })

        except Exception as e:
            print(f"[!] Lỗi khi cào trang: {e}")
        finally:
            browser.close()

    # Xuất file M3U theo chính xác định dạng mẫu
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")

        for ch in parsed_channels:
            logo_attr = f'tvg-logo="{ch["logo"]}"' if ch["logo"] else ''
            
            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}" , {ch["title"]}\n')
            f.write(f'#EXTVLCOPT:http-referrer={REFERRER_HEADER}\n')
            f.write(f'{ch["url"]}\n\n')

    print(f"[*] Đã xuất thành công {len(parsed_channels)} kênh vào {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
