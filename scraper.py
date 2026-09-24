import time
import re
from urllib.parse import quote
from playwright.sync_api import sync_playwright

BASE_URL = "https://phalang.live"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Phá Làng TV"
REFERRER_HEADER = "https://phalang.live/"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

def get_fallback_logo(team_name: str) -> str:
    """Bộ tra cứu cờ quốc gia nét HD làm dự phòng khi logo trang web bị thiếu"""
    t = team_name.lower().strip()
    logos = {
        "japan": "https://flagcdn.com/w320/jp.png",
        "uruguay": "https://flagcdn.com/w320/uy.png",
        "laos": "https://flagcdn.com/w320/la.png",
        "brunei": "https://flagcdn.com/w320/bn.png",
        "south korea": "https://flagcdn.com/w320/kr.png",
        "korea": "https://flagcdn.com/w320/kr.png",
        "ecuador": "https://flagcdn.com/w320/ec.png",
        "myanmar": "https://flagcdn.com/w320/mm.png",
        "timor": "https://flagcdn.com/w320/tl.png",
        "uzbekistan": "https://flagcdn.com/w320/uz.png",
        "iran": "https://flagcdn.com/w320/ir.png",
        "uae": "https://flagcdn.com/w320/ae.png",
        "yemen": "https://flagcdn.com/w320/ye.png",
        "vietnam": "https://flagcdn.com/w320/vn.png",
        "thailand": "https://flagcdn.com/w320/th.png",
        "indonesia": "https://flagcdn.com/w320/id.png",
        "malaysia": "https://flagcdn.com/w320/my.png",
        "china": "https://flagcdn.com/w320/cn.png",
        "australia": "https://flagcdn.com/w320/au.png",
        "brazil": "https://flagcdn.com/w320/br.png"
    }
    for k, url in logos.items():
        if k in t:
            return url
    return "https://flagcdn.com/w320/un.png"

def clean_text_and_hashes(text: str) -> str:
    """Lọc sạch triệt để các chuỗi mã rác ID (như 2Y8M4Zhv0177QIO, 318q66h8z4poqo9)"""
    # Xóa các chuỗi mã ngẫu nhiên có độ dài từ 8 đến 35 ký tự
    cleaned = re.sub(r'[a-zA-Z0-9]{8,35}', '', text)
    # Làm sạch khoảng trắng dư thừa
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def run_scraper():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 8000}, # Chiều cao lớn để load hết trận
            timezone_id="Asia/Ho_Chi_Minh",
            locale="vi-VN"
        )
        page = context.new_page()

        parsed_channels = []

        try:
            print(f"[*] Đang tải trang chủ: {BASE_URL}")
            page.goto(BASE_URL, timeout=50000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            # Cuộn trang tự động xuống dưới để load sạch 100% tất cả các trận đấu
            print("[*] Đang cuộn trang để lấy toàn bộ danh sách trận đấu...")
            page.evaluate("""async () => {
                await new Promise((resolve) => {
                    let totalHeight = 0;
                    let distance = 500;
                    let timer = setInterval(() => {
                        let scrollHeight = document.body.scrollHeight;
                        window.scrollBy(0, distance);
                        totalHeight += distance;
                        if(totalHeight >= scrollHeight){
                            clearInterval(timer);
                            resolve();
                        }
                    }, 150);
                });
            }""")
            page.wait_for_timeout(2000)

            # Bóc tách tất cả thẻ trận đấu
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

                    // Lấy logo từ thẻ img hoặc data-src
                    const img = card.querySelector('img');
                    let logo = '';
                    if (img) {
                        logo = img.src || img.getAttribute('data-src') || img.getAttribute('data-original') || '';
                    }

                    const text = card.innerText || card.parentElement.innerText || '';

                    results.push({
                        url: fullUrl,
                        logo: logo,
                        rawText: text
                    });
                });
                return results;
            }''')

            print(f"[*] Tìm thấy tổng cộng {len(matches_data)} trận đấu. Bắt đầu lấy luồng stream...")

            for idx, item in enumerate(matches_data):
                match_url = item['url']
                logo = item['logo']
                text = clean_text_and_hashes(item['rawText'])

                detail_page = context.new_page()
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
                    time.sleep(3)
                except Exception:
                    pass
                finally:
                    detail_page.close()

                if not m3u8_list:
                    continue

                # Xác định thời gian & Trạng thái
                status_icon = ""
                if "trực tiếp" in text.lower() or "live" in text.lower() or "đang diễn ra" in text.lower():
                    status_icon = "🟢 "
                elif "sắp diễn ra" in text.lower():
                    status_icon = "🟡 "

                time_match = re.search(r'(\d{1,2}[:h]\d{2})\s*(\d{1,2}/\d{1,2})?', text)
                time_str = ""
                if time_match:
                    t_val = time_match.group(1).replace('h', ':')
                    d_val = f" {time_match.group(2)}" if time_match.group(2) else ""
                    time_str = f"{t_val}{d_val} "

                blv_match = re.search(r'\(([^)]*BLV[^)]*)\)|\b((?:LÝ|BLV|GA)\s+[A-Za-zÀ-ỹ0-9\s]+)', text, re.I)
                blv_str = f" ({blv_match.group(1) or blv_match.group(2)})" if blv_match else ""

                # Tách tên 2 đội & xử lý Logo
                teams_title = "Trận đấu Trực Tiếp"
                first_team_name = ""
                slug_match = re.search(r'/(?:truc-tiep|match|live)/([^/?#]+)', match_url)
                if slug_match:
                    parts = slug_match.group(1).split('-vs-')
                    if len(parts) == 2:
                        t1 = clean_text_and_hashes(re.sub(r'^(?:blv-)?ga-(?:sieu-)?[a-z0-9]+-', '', parts[0], flags=re.I)).replace('-', ' ').title()
                        t2 = clean_text_and_hashes(parts[1]).replace('-', ' ').title()
                        teams_title = f"{t1} vs {t2}"
                        first_team_name = t1

                # Nếu logo web bị trống thì lấy logo dự phòng
                if not logo or "data:image" in logo:
                    logo = get_fallback_logo(first_team_name)

                base_title = f"{status_icon}{time_str}⚽ {teams_title}{blv_str}".strip()

                # Xuất đủ các bản luồng (HD1, HD2, Nhà đài)
                for m3u8_url in m3u8_list:
                    sub_tag = ""
                    if "pull1.digitalcdn.net" in m3u8_url:
                        sub_tag = " (HD2)"
                    elif "lilive" in m3u8_url or "eu.cc" in m3u8_url:
                        sub_tag = " (Nhà đài)"

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

    # Xuất file M3U kèm Pipe Header kép
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")

        for ch in parsed_channels:
            logo_attr = f'tvg-logo="{ch["logo"]}"' if ch["logo"] else ''
            
            # Gắn trực tiếp Header vào đuôi URL để TiviMate không bị chặn CDN
            stream_url_with_headers = f"{ch['url']}|Referer={quote(REFERRER_HEADER)}&User-Agent={quote(USER_AGENT)}"
            
            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}" , {ch["title"]}\n')
            f.write(f'#EXTVLCOPT:http-referrer={REFERRER_HEADER}\n')
            f.write(f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n')
            f.write(f'{stream_url_with_headers}\n\n')

    print(f"[*] Đã xuất thành công {len(parsed_channels)} kênh vào {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
