import re
from urllib.parse import quote
from playwright.sync_api import sync_playwright

BASE_URL = "https://phalang.tv"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Phà Lăng TV"

# CHÚ Ý: Anh Sơn thay dòng này bằng đường dẫn Cloudflare Worker thực tế của anh
WORKER_URL = "https://cctv.sonnguyen90pro.workers.dev/live?url="

def get_team_logo_url(team_name: str) -> str:
    t_lower = team_name.lower().strip()
    logos = {
        "laos": "https://flagcdn.com/w320/la.png",
        "brunei": "https://flagcdn.com/w320/bn.png",
        "vietnam": "https://flagcdn.com/w320/vn.png",
        "thailand": "https://flagcdn.com/w320/th.png",
        "indonesia": "https://flagcdn.com/w320/id.png",
        "malaysia": "https://flagcdn.com/w320/my.png",
        "japan": "https://flagcdn.com/w320/jp.png",
        "south korea": "https://flagcdn.com/w320/kr.png"
        # Anh có thể bổ sung thêm logo các đội bóng khác tại đây
    }
    for key, url in logos.items():
        if key in t_lower:
            return url
    return "https://flagcdn.com/w320/fk.png"

def parse_teams_from_url(url: str) -> tuple:
    try:
        match = re.search(r'/(?:truc-tiep|match|live)/([^/?#]+)', url)
        if not match: return "", ""
        slug = match.group(1)
        parts = slug.split('-vs-')
        if len(parts) != 2: return "", ""
        
        team1_slug, team2_slug = parts[0], parts[1]
        team1_slug = re.sub(r'^(?:blv-)?ga-(?:sieu-)?[a-z0-9]+-', '', team1_slug, flags=re.IGNORECASE)
        team2_slug = re.sub(r'-luc-\d+.*$', '', team2_slug, flags=re.IGNORECASE)
        team2_slug = re.sub(r'-ngay-\d+.*$', '', team2_slug, flags=re.IGNORECASE)
        
        def clean_word(w):
            w_low = w.lower()
            if w_low in ['nu', 'nữ']: return 'Nữ'
            if w_low in ['nam']: return 'Nam'
            if w_low in ['u23', 'u21', 'u20', 'u19', 'u18', 'u17']: return w.upper()
            return w.capitalize()

        t1 = " ".join([clean_word(w) for w in team1_slug.split('-')])
        t2 = " ".join([clean_word(w) for w in team2_slug.split('-')])
        
        if t1 and t2:
            return f"{t1} vs {t2}", t1
    except:
        pass
    return "", ""

def run_scraper():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()

        try:
            print(f"[*] Đang tải trang chủ: {BASE_URL}")
            page.goto(BASE_URL, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            # Chỉ cào link ở trang chủ, KHÔNG truy cập vào từng trận
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

                    // Lấy toàn bộ chữ hiển thị trên thẻ trận đấu
                    const fullText = link.parentElement.innerText || link.innerText || '';
                    matches.push({ url: fullUrl, fullText: fullText });
                });
                return matches;
            }''')
        except Exception as e:
            print(f"[!] Lỗi khi cào trang: {e}")
            raw_matches = []
        finally:
            browser.close()

    # Xử lý thông tin hiển thị
    parsed_items = []
    for item in raw_matches:
        url = item['url']
        text = item['fullText']
        
        # Trích xuất thời gian từ chữ trên trang chủ
        time_match = re.search(r'\b(\d{1,2}[:h]\d{2})\b', text, re.I)
        time_str = f"{time_match.group(1).replace('h', ':')} Hôm nay" if time_match else "Sắp diễn ra"

        # Trích xuất BLV
        blv_name = ""
        blv_match = re.search(r'((?:Gà|BLV)\s+[A-Za-zÀ-ỹ0-9\s\+]+)', text, re.IGNORECASE)
        if blv_match:
            blv_name = re.split(r'(?:hls|flv|live|trực tiếp)', blv_match.group(1), flags=re.IGNORECASE)[0].strip()
        clean_blv = re.sub(r'^(BLV|Caster)\s*[:\-]?\s*', '', blv_name, flags=re.IGNORECASE).strip()
        blv_suffix = f" (BLV {clean_blv.title()})" if clean_blv else ""

        # Lấy tên đội
        teams_str, team1_name = parse_teams_from_url(url)
        if not teams_str:
            teams_str = "Trận đấu Trực Tiếp"

        logo = get_team_logo_url(team1_name)
        full_title = f"{time_str} ⚽ {teams_str}{blv_suffix}".strip()

        parsed_items.append({
            "title": full_title,
            "logo": logo,
            "url": url
        })

    # Ghi file M3U với cú pháp bọc qua Worker
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")
        
        for item in parsed_items:
            logo_attr = f'tvg-logo="{item["logo"]}"' if item["logo"] else ''
            
            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}",{item["title"]}\n')
            
            # ĐÂY LÀ ĐIỂM QUAN TRỌNG NHẤT:
            # Gắn link web gốc vào sau link Worker.
            # TiviMate sẽ gọi Worker -> Worker mới là người đi lấy link m3u8.
            stream_url_via_worker = f"{WORKER_URL}{item['url']}"
            f.write(f'{stream_url_via_worker}\n\n')

    print(f"[*] Đã xuất thành công {len(parsed_items)} trận vào {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
