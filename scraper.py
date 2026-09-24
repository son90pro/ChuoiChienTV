import time
import re
from urllib.parse import quote
from playwright.sync_api import sync_playwright

BASE_URL = "https://phalang.tv"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Phá Làng TV"

# Mã giả lập trình duyệt Chrome tiêu chuẩn
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

def get_team_logo_url(team_name: str) -> str:
    """Tra cứu logo quốc gia chuẩn xác"""
    t_lower = team_name.lower().strip()
    logos = {
        "japan": "https://flagcdn.com/w320/jp.png",
        "uruguay": "https://flagcdn.com/w320/uy.png",
        "laos": "https://flagcdn.com/w320/la.png",
        "brunei": "https://flagcdn.com/w320/bn.png",
        "south korea": "https://flagcdn.com/w320/kr.png",
        "ecuador": "https://flagcdn.com/w320/ec.png",
        "myanmar": "https://flagcdn.com/w320/mm.png",
        "timor leste": "https://flagcdn.com/w320/tl.png",
        "uzbekistan": "https://flagcdn.com/w320/uz.png",
        "iran": "https://flagcdn.com/w320/ir.png",
        "ir iran": "https://flagcdn.com/w320/ir.png",
        "united arab emirates": "https://flagcdn.com/w320/ae.png",
        "uae": "https://flagcdn.com/w320/ae.png",
        "yemen": "https://flagcdn.com/w320/ye.png",
        "palestine": "https://flagcdn.com/w320/ps.png",
        "new zealand": "https://flagcdn.com/w320/nz.png",
        "china": "https://flagcdn.com/w320/cn.png",
        "vietnam": "https://flagcdn.com/w320/vn.png",
        "thailand": "https://flagcdn.com/w320/th.png",
        "indonesia": "https://flagcdn.com/w320/id.png",
        "malaysia": "https://flagcdn.com/w320/my.png"
    }
    for key, url in logos.items():
        if key in t_lower:
            return url
    return "https://flagcdn.com/w320/fk.png"

def parse_teams_from_url(url: str) -> tuple:
    """Lọc sạch tên 2 đội bóng và xóa triệt để mã ID ngẫu nhiên (như 318q66h8z4poqo9)"""
    try:
        match = re.search(r'/(?:truc-tiep|match|live)/([^/?#]+)', url)
        if not match:
            return "", ""
        slug = match.group(1)
        
        parts = slug.split('-vs-')
        if len(parts) != 2:
            return "", ""
        
        team1_slug, team2_slug = parts[0], parts[1]
        
        # Xóa tiền tố BLV/Gà
        team1_slug = re.sub(r'^(?:blv-)?ga-(?:sieu-)?[a-z0-9]+-', '', team1_slug, flags=re.IGNORECASE)
        
        # Xóa hậu tố thời gian và mã rác ID ngẫu nhiên ở cuối
        team2_slug = re.sub(r'-luc-\d+.*$', '', team2_slug, flags=re.IGNORECASE)
        team2_slug = re.sub(r'-ngay-\d+.*$', '', team2_slug, flags=re.IGNORECASE)
        team2_slug = re.sub(r'-[a-z0-9]{8,35}$', '', team2_slug, flags=re.IGNORECASE)
        
        def clean_word(w):
            w_low = w.lower()
            if w_low in ['nu', 'nữ']: return 'Nữ'
            if w_low in ['nam']: return 'Nam'
            if w_low in ['u23', 'u21', 'u20', 'u19', 'u18', 'u17']: return w.upper()
            return w.capitalize()

        t1 = " ".join([clean_word(w) for w in team1_slug.split('-') if w])
        t2 = " ".join([clean_word(w) for w in team2_slug.split('-') if w])
        
        if t1 and t2:
            return f"{t1} vs {t2}", t1
    except Exception:
        pass
    return "", ""

def get_live_m3u8(context, match_url: str) -> str:
    """Mở trang trận đấu và chộp lấy link m3u8 phát ra từ trình duyệt"""
    page = context.new_page()
    # Chặn ảnh/css để tải trang nhanh tối đa
    page.route("**/*.{png,jpg,jpeg,svg,css,woff,woff2,gif}", lambda route: route.abort())
    
    m3u8_found = []
    def handle_request(request):
        url = request.url
        if ".m3u8" in url and "blob:" not in url:
            m3u8_found.append(url)

    page.on("request", handle_request)

    try:
        page.goto(match_url, timeout=15000, wait_until="domcontentloaded")
        # Chờ tối đa 6 giây để trình duyệt load xong luồng video
        for _ in range(12):
            if m3u8_found:
                break
            time.sleep(0.5)
    except Exception:
        pass
    finally:
        page.close()

    # Trả về link m3u8 bắt được cuối cùng (tránh link mồi/quảng cáo)
    return m3u8_found[-1] if m3u8_found else ""

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

        raw_matches = []
        try:
            print(f"[*] Đang tải trang chủ: {BASE_URL}")
            page.goto(BASE_URL, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            raw_matches = page.evaluate('''() => {
                const matches = [];
                const links = Array.from(document.querySelectorAll('a[href*="/truc-tiep/"], a[href*="/match/"], a[href*="/live/"]'));
                const seenUrls = new Set();

                links.forEach(link => {
                    const href = link.getAttribute('href');
                    if (!href) return;

                    const fullUrl = href.startsWith('http') ? href : window.location.origin + href;
                    if (seenUrls.has(fullUrl)) return;
                    seenUrls.add(fullUrl);

                    const fullText = link.parentElement ? link.parentElement.innerText || '' : link.innerText || '';

                    matches.push({
                        url: fullUrl,
                        fullText: fullText
                    });
                });

                return matches;
            }''')
        except Exception as e:
            print(f"[!] Lỗi cào trang chủ: {e}")
        finally:
            page.close()

        parsed_items = []
        for idx, item in enumerate(raw_matches):
            text = item['fullText']
            url = item['url']

            # Tên 2 đội & Logo
            teams_str, team1_name = parse_teams_from_url(url)
            if not teams_str:
                continue

            print(f"[*] [{idx+1}/{len(raw_matches)}] Đang bắt luồng: {teams_str}")
            real_m3u8 = get_live_m3u8(context, url)

            # Thời gian hoặc trạng thái
            time_match = re.search(r'\b(\d{1,2}[:h]\d{2})\b', text, re.I)
            time_str = f"{time_match.group(1).replace('h', ':')}" if time_match else "Trực tiếp"

            logo = get_team_logo_url(team1_name)
            full_title = f"{time_str} ⚽ {teams_str}".strip()

            parsed_items.append({
                "title": full_title,
                "logo": logo,
                "m3u8": real_m3u8
            })

        browser.close()

    # Xuất file playlist M3U với mã ngụy trang Pipe chuẩn TiviMate
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")

        for item in parsed_items:
            if not item["m3u8"]:
                continue

            logo_attr = f'tvg-logo="{item["logo"]}"' if item["logo"] else ''
            
            # Đính kèm Headers ngụy trang trực tiếp vào sau link qua dấu |
            stream_url = f"{item['m3u8']}|Referer={BASE_URL}/&Origin={BASE_URL}&User-Agent={quote(USER_AGENT)}"
            
            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}",{item["title"]}\n')
            f.write(f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n')
            f.write(f'#EXTVLCOPT:http-referrer={BASE_URL}/\n')
            f.write(f'#EXTVLCOPT:http-origin={BASE_URL}\n')
            f.write(f'{stream_url}\n\n')

    print(f"[*] Đã xuất thành công {len(parsed_items)} luồng live vào {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
