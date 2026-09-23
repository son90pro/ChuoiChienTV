import time
import re
from urllib.parse import quote
from playwright.sync_api import sync_playwright

# Tên miền Cloudflare Worker của anh Sơn
WORKER_DOMAIN = "cctv.sonnguyen90pro.workers.dev"

# Chỉ lấy nguồn duy nhất từ Chuối Chiên TV
BASE_URL = "https://chuoichientv.com"

OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Chuối Chiên TV"
DEFAULT_LOGO = "https://raw.githubusercontent.com/iptv-org/iptv/master/logos/sports.png"

# Danh sách từ khóa giải đấu cần lọc khỏi tên đội bóng
LEAGUE_KEYWORDS = [
    'league', 'cup', 'championship', 'world cup', 'v-league', 'v league',
    'premier', 'la liga', 'serie a', 'bundesliga', 'ligue', 'cúp', 'giải',
    'copa', 'euro', 'afc', 'uefa', 'concacaf', 'waff', 'usl', 'nba', 'kbo',
    'champions', 'europa', 'nations', 'trophy', 'shield', 'super cup'
]

STATUS_KEYWORDS = [
    'hiệp 1', 'hiệp 2', 'h1', 'h2', 'ft', 'ht', 'full time', 'half time',
    'đang diễn ra', 'trực tiếp', 'phút', 'sắp diễn ra', 'live', 'xem ngay',
    'hls', 'flv', 'server', 'hd', 'fhd'
]

def is_league_or_status(text):
    if not text:
        return True
    t_lower = text.strip().lower()
    if len(t_lower) < 2:
        return True
    if re.match(r'^\d{1,2}:\d{2}$', t_lower) or re.match(r'^\d{1,2}/\d{1,2}$', t_lower):
        return True
    for kw in STATUS_KEYWORDS:
        if kw in t_lower:
            return True
    for kw in LEAGUE_KEYWORDS:
        if kw in t_lower:
            return True
    return False

def parse_match_card(text, raw_logo):
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    # Trích xuất thời gian
    time_match = re.search(r'(\d{1,2}:\d{2})', text)
    date_match = re.search(r'(\d{1,2}/\d{1,2})', text)
    m_time = time_match.group(1) if time_match else ("LIVE" if "LIVE" in text.upper() or "TRỰC TIẾP" in text.upper() else "")
    m_date = date_match.group(1) if date_match else ""
    time_str = f"{m_time} {m_date}".strip() or "LIVE"

    # Trích xuất tên BLV
    blv_str = ""
    blv_match = re.search(r'(?:BLV|Chuối)\s+([A-Za-zÀ-ỹ0-9\s]+)', text, re.IGNORECASE) or re.search(r'\(([^)]+)\)', text)
    if blv_match:
        blv_name = blv_match.group(0).replace('(', '').replace(')', '').strip()
        if any(k in blv_name.lower() for k in ['chuối', 'blv']):
            blv_str = f" ({blv_name})"

    # Phân tích tên hai đội bóng
    teams_str = ""
    vs_idx = -1
    for idx, line in enumerate(lines):
        if line.lower() in ['vs', 'v.s', '-']:
            vs_idx = idx
            break

    if vs_idx != -1:
        home_team = ""
        for i in range(vs_idx - 1, -1, -1):
            if not is_league_or_status(lines[i]):
                home_team = lines[i]
                break
        
        away_team = ""
        for i in range(vs_idx + 1, len(lines)):
            if not is_league_or_status(lines[i]):
                away_team = lines[i]
                break

        if home_team and away_team:
            teams_str = f"{home_team} vs {away_team}"
        elif home_team or away_team:
            teams_str = home_team or away_team

    if not teams_str:
        valid_lines = [l for l in lines if not is_league_or_status(l)]
        if len(valid_lines) >= 2:
            teams_str = f"{valid_lines[0]} vs {valid_lines[1]}"
        elif len(valid_lines) == 1:
            teams_str = valid_lines[0]
        else:
            if blv_str:
                clean_blv = blv_str.replace('(', '').replace(')', '').strip()
                teams_str = f"Kênh BLV {clean_blv}"
                blv_str = ""
            else:
                teams_str = "Trận đấu Trực Tiếp"

    title = f"{time_str} ⚽ {teams_str}{blv_str}"
    logo = raw_logo if raw_logo else DEFAULT_LOGO

    return title, logo

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

        final_matches = []
        page = context.new_page()

        try:
            print(f"[*] Đang tải Chuối Chiên TV: {BASE_URL}")
            page.goto(BASE_URL, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)

            raw_matches = page.evaluate('''() => {
                const matches = [];
                const cards = Array.from(document.querySelectorAll('.match-item, .card-match, .item-match, div[class*="match"], div[class*="card"], a[href*="/truc-tiep/"], a[href*="/match/"], a[href*="/xem/"]'));

                cards.forEach(card => {
                    const linkEl = card.tagName === 'A' ? card : (card.querySelector('a[href*="/truc-tiep/"], a[href*="/match/"], a[href*="/xem/"]') || card.querySelector('a'));
                    if (!linkEl) return;

                    const href = linkEl.getAttribute('href');
                    if (!href || href === '#' || href.startsWith('javascript')) return;

                    let logo = '';
                    const imgs = Array.from(card.querySelectorAll('img'));
                    for (let img of imgs) {
                        let src = img.getAttribute('src') || img.getAttribute('data-src') || img.getAttribute('data-lazy-src') || '';
                        if (src && !src.includes('favicon') && !src.includes('icon-') && !src.includes('bg-')) {
                            logo = src.startsWith('http') ? src : window.location.origin + src;
                            break;
                        }
                    }

                    matches.push({
                        url: href.startsWith('http') ? href : window.location.origin + href,
                        logo: logo,
                        fullText: card.innerText || ''
                    });
                });

                return matches;
            }''')

            unique_matches = {}
            for item in raw_matches:
                url = item['url']
                text = item['fullText']
                if not text or url in unique_matches:
                    continue

                title, logo = parse_match_card(text, item['logo'])

                unique_matches[url] = {
                    "title": title,
                    "logo": logo,
                    "url": url
                }

            match_list = list(unique_matches.values())
            page.close()

            print(f"[*] Tìm thấy {len(match_list)} trận từ Chuối Chiên TV. Đang bóc tách link M3U8...")
            for idx, match in enumerate(match_list):
                print(f"[{idx+1}/{len(match_list)}] Lấy link: {match['title']}")
                m3u8_url = get_m3u8_for_match(context, match['url'])
                match['m3u8_url'] = m3u8_url

            final_matches = match_list

        except Exception as e:
            print(f"[!] Lỗi khi cào dữ liệu Chuối Chiên TV: {e}")
            page.close()

        browser.close()

    # Xuất file playlist.m3u
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")

        for item in final_matches:
            logo_attr = f'tvg-logo="{item["logo"]}"' if item["logo"] else ''
            ref_url = "https://chuoichientv.com"

            if item.get('m3u8_url'):
                encoded_m3u8 = quote(item['m3u8_url'], safe='')
                encoded_ref = quote(ref_url + '/', safe='')
                stream_url = f"https://{WORKER_DOMAIN}/proxy?url={encoded_m3u8}&referer={encoded_ref}"
            else:
                stream_url = f"https://{WORKER_DOMAIN}/proxy?url={quote(item['url'], safe='')}"
            
            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}",{item["title"]}\n')
            f.write(f'{stream_url}\n\n')

    print(f"[*] Hoàn tất xuất file {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
