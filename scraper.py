import time
import re
from datetime import datetime
from urllib.parse import urljoin, quote
from playwright.sync_api import sync_playwright

BASE_URL = "https://phalang.live"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Phá Làng TV"
REFERRER_HEADER = "https://phalang.live/"

# Đã đổi WORKER_DOMAIN mới theo yêu cầu
WORKER_DOMAIN = "pha-lang-iptv.sonnguyen90pro.workers.dev"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Bảng tra cứu cờ quốc gia chuẩn HD theo Đội 1
FLAG_LOGOS = {
    "china": "https://flagcdn.com/w320/cn.png",
    "trung quốc": "https://flagcdn.com/w320/cn.png",
    "vietnam": "https://flagcdn.com/w320/vn.png",
    "việt nam": "https://flagcdn.com/w320/vn.png",
    "bangladesh": "https://flagcdn.com/w320/bd.png",
    "malaysia": "https://flagcdn.com/w320/my.png",
    "australia": "https://flagcdn.com/w320/au.png",
    "úc": "https://flagcdn.com/w320/au.png",
    "brazil": "https://flagcdn.com/w320/br.png",
    "japan": "https://flagcdn.com/w320/jp.png",
    "nhật bản": "https://flagcdn.com/w320/jp.png",
    "philippines": "https://flagcdn.com/w320/ph.png",
    "south korea": "https://flagcdn.com/w320/kr.png",
    "hàn quốc": "https://flagcdn.com/w320/kr.png",
    "indonesia": "https://flagcdn.com/w320/id.png",
    "singapore": "https://flagcdn.com/w320/sg.png",
    "thailand": "https://flagcdn.com/w320/th.png",
    "thái lan": "https://flagcdn.com/w320/th.png"
}

def clean_team_name(name: str) -> str:
    """Xử lý làm sạch tên đội bóng từ slug"""
    if not name:
        return ""
    s = re.sub(r'^(?:blv|caster|ga)-[a-z0-9]+-', '', name, flags=re.I)
    s = re.sub(r'-(?:luc|ngay|[a-z0-9]{8,}).*$', '', s, flags=re.I)
    s = s.replace('-', ' ').strip().title()
    return s

def process_logo_url(raw_logo: str, team1_name: str, teams_title: str) -> str:
    """Ưu tiên ghép cờ theo Đội 1"""
    t1_lower = team1_name.lower().strip()
    for k, v in FLAG_LOGOS.items():
        if k in t1_lower:
            return v
            
    t_lower = teams_title.lower()
    for k, v in FLAG_LOGOS.items():
        if k in t_lower:
            return v
    
    if raw_logo and not raw_logo.startswith("data:image"):
        if raw_logo.startswith("//"):
            return "https:" + raw_logo
        elif raw_logo.startswith("http"):
            return raw_logo
        elif raw_logo.startswith("/"):
            return urljoin(BASE_URL, raw_logo)
            
    return "https://flagcdn.com/w320/un.png"

def parse_time_and_date(card_text: str, match_url: str, detail_text: str, default_date: str) -> str:
    """Trích xuất thời gian đầy đủ cho mọi trận đấu"""
    for text in [card_text, detail_text]:
        if not text:
            continue
        time_match = re.search(r'\b(\d{1,2}[:h]\d{2})\b(?:\s*[-–/]?\s*(\d{1,2}/\d{1,2}))?', text)
        if time_match:
            t_val = time_match.group(1).replace('h', ':')
            if len(t_val.split(':')[0]) == 1:
                t_val = "0" + t_val
            d_val = time_match.group(2) if time_match.group(2) else default_date
            return f"{t_val} {d_val}"

    url_time = re.search(r'(?:luc|h|-)(\d{1,2})h(\d{2})', match_url, re.I)
    url_date = re.search(r'(?:ngay|-)(\d{1,2})[-/](\d{1,2})', match_url, re.I)
    if url_time:
        t_u = f"{int(url_time.group(1)):02d}:{url_time.group(2)}"
        d_u = f"{int(url_date.group(1)):02d}/{int(url_date.group(2)):02d}" if url_date else default_date
        return f"{t_u} {d_u}"

    return f"13:00 {default_date}"

def parse_blv_name(card_text: str, match_url: str, detail_text: str) -> str:
    """Bóc tên BLV"""
    slug_blv = re.search(r'/(?:truc-tiep|match|live)/.*?blv-([a-z0-9-]+?)-(?:vs|[a-z0-9]+-vs)', match_url, re.I)
    if slug_blv:
        return slug_blv.group(1).replace('-', ' ').upper()

    combined_text = f"{card_text}\n{detail_text}"
    match = re.search(r'\b((?:BLV|Caster|Bình Luận Viên|Gà|Lý)\s+[A-Za-zÀ-ỹ0-9\s]+)\b', combined_text, re.I)
    if match:
        blv = match.group(1).strip()
        blv = re.sub(r'^(?:Bình Luận Viên|Caster|Gà)\s*', '', blv, flags=re.I)
        return blv.upper()
        
    return "PHÁ LÀNG"

def run_scraper():
    today_str = datetime.now().strftime("%d/%m")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 3000},
            timezone_id="Asia/Ho_Chi_Minh",
            locale="vi-VN"
        )
        page = context.new_page()
        matches_list = []

        try:
            print(f"[*] Đang tải trang chủ Phá Làng TV: {BASE_URL}")
            page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
            time.sleep(3)

            for _ in range(5):
                page.evaluate("window.scrollBy(0, 800)")
                time.sleep(0.5)

            raw_cards = page.evaluate('''() => {
                const results = [];
                const selector = 'a[href*="/truc-tiep/"], a[href*="/xem-truc-tiep/"], a[href*="/match/"], a[href*="/live/"], a[href*="/tran/"]';
                const cards = document.querySelectorAll(selector);
                const seenUrls = new Set();

                cards.forEach(card => {
                    const href = card.getAttribute('href');
                    if (!href) return;
                    const fullUrl = href.startsWith('http') ? href : window.location.origin + href;
                    if (seenUrls.has(fullUrl)) return;
                    seenUrls.add(fullUrl);

                    let container = card;
                    let parent = card.parentElement;
                    while (parent && parent.tagName !== 'BODY') {
                        if (parent.querySelectorAll(selector).length > 1) break;
                        container = parent;
                        parent = parent.parentElement;
                    }

                    let logo = '';
                    const img = container.querySelector('img');
                    if (img) {
                        logo = img.src || img.getAttribute('data-src') || img.getAttribute('data-original') || '';
                    }

                    results.push({
                        url: fullUrl,
                        logo: logo,
                        rawText: container.innerText || card.innerText || ''
                    });
                });
                return results;
            }''')

            print(f"[*] Tìm thấy {len(raw_cards)} trận đấu. Đang bóc tách luồng qua worker {WORKER_DOMAIN}...")

            for item in raw_cards:
                match_url = item['url']
                raw_logo = item['logo']
                card_text = item['rawText']

                team1_name = ""
                teams_title = ""
                slug_match = re.search(r'/(?:truc-tiep|xem-truc-tiep|match|live|tran)/([^/?#]+)', match_url)
                if slug_match:
                    slug = slug_match.group(1)
                    if "-vs-" in slug:
                        parts = slug.split('-vs-')
                        t1 = clean_team_name(parts[0])
                        t2 = clean_team_name(parts[1])
                        if t1 and t2:
                            team1_name = t1
                            teams_title = f"{t1} vs {t2}"

                if not teams_title:
                    lines = [l.strip() for l in card_text.split('\n') if l.strip()]
                    team_lines = [l for l in lines if not re.search(r'(\d{1,2}:\d{2}|sắp diễn ra|trực tiếp|live)', l, re.I)]
                    if len(team_lines) >= 2:
                        team1_name = team_lines[0]
                        teams_title = f"{team_lines[0]} vs {team_lines[1]}"
                    else:
                        teams_title = "Trận đấu Trực Tiếp"

                final_logo = process_logo_url(raw_logo, team1_name, teams_title)

                detail_page = context.new_page()
                m3u8_captured = []
                detail_text = ""

                def handle_req(req):
                    u = req.url
                    if ".m3u8" in u and "blob:" not in u and u not in m3u8_captured:
                        m3u8_captured.append(u)

                detail_page.on("request", handle_req)

                try:
                    detail_page.goto(match_url, timeout=12000, wait_until="domcontentloaded")
                    time.sleep(2)
                    detail_text = detail_page.evaluate("document.body ? document.body.innerText : ''")

                    server_buttons = detail_page.query_selector_all("button, .server-item, .btn-server")
                    for btn in server_buttons[:3]:
                        try:
                            btn.click(timeout=1000)
                            time.sleep(1)
                        except Exception:
                            pass

                    if not m3u8_captured:
                        html_content = detail_page.content()
                        found_m3u8 = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html_content)
                        for f_url in found_m3u8:
                            if "blob:" not in f_url and f_url not in m3u8_captured:
                                m3u8_captured.append(f_url)
                except Exception:
                    pass
                finally:
                    detail_page.close()

                time_str = parse_time_and_date(card_text, match_url, detail_text, today_str)
                blv_name = parse_blv_name(card_text, match_url, detail_text)
                base_title = f"{time_str} ⚽ {teams_title} ({blv_name}) [geo]".strip()

                if m3u8_captured:
                    for stream_url in m3u8_captured:
                        matches_list.append({
                            "title": base_title,
                            "logo": final_logo,
                            "url": f"https://{WORKER_DOMAIN}/proxy?url={quote(stream_url, safe='')}"
                        })
                else:
                    fallback_proxy = f"https://{WORKER_DOMAIN}/live?url={quote(match_url, safe='')}"
                    matches_list.append({
                        "title": base_title,
                        "logo": final_logo,
                        "url": fallback_proxy
                    })

        except Exception as e:
            print(f"[!] Lỗi khi cào dữ liệu: {e}")
        finally:
            browser.close()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")

        for item in matches_list:
            logo_attr = f'tvg-logo="{item["logo"]}"' if item["logo"] else ''
            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}",{item["title"]}\n')
            f.write(f'#EXTVLCOPT:http-referrer={REFERRER_HEADER}\n')
            f.write(f'{item["url"]}\n\n')

    print(f"[*] Đã xuất thành công {len(matches_list)} trận vào {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
