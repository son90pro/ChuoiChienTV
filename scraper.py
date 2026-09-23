import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

DOMAINS = [
    "https://chuoichien.tv",
    "https://bonglautv.pro",
    "https://chuoichientv1.link",
    "https://chuoichientv.com"
]

OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Chuối Chiến TV"

# Danh sách từ khóa giải đấu cần lọc sạch khỏi tên đội và BLV
TOURNAMENT_KEYWORDS = [
    "world cup", "asian games", "emperor's cup", "emperor", "jfa", "championship",
    "v-league", "premier league", "champions league", "euro", "copa", "afc", "fifa",
    "uefa", "serie", "liga", "bundesliga", "u20", "u23", "u19", "u17", "women", "nữ",
    "cúp", "cup", "giải", "bảng", "vòng"
]

SLOGAN_KEYWORDS = [
    "giúp bạn", "toàn diện", "thế giới", "bản quyền", "hệ thống", 
    "trải nghiệm", "chất lượng", "miễn phí", "liên hệ", "đăng ký", 
    "khuyến mãi", "chuoichien", "bonglau", "người xem", "phát sóng",
    "uy lực", "soi kèo", "đặt cược", "tốc độ", "tải trang", "cam kết"
]

FILTER_KEYWORDS = TOURNAMENT_KEYWORDS + SLOGAN_KEYWORDS + [
    "live", "trực tiếp", "hls", "flv", "xem ngay", "phút"
]

def clean_str(t):
    return re.sub(r'\s+', ' ', t or '').strip()

def is_invalid_text(text):
    t_lower = text.lower()
    return any(kw in t_lower for kw in SLOGAN_KEYWORDS)

def is_tournament(text):
    t_lower = text.lower().strip()
    return any(kw == t_lower or kw in t_lower for kw in TOURNAMENT_KEYWORDS)

def run_scraper():
    today_str = datetime.now().strftime("%d/%m")
    parsed_matches = []
    seen_keys = set()
    active_domain = DOMAINS[0]

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            timezone_id="Asia/Ho_Chi_Minh",
            locale="vi-VN"
        )
        page = context.new_page()

        raw_items = []
        for domain in DOMAINS:
            try:
                print(f"[*] Kết nối tới: {domain}")
                page.goto(domain, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)

                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                page.wait_for_timeout(1000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500)

                raw_items = page.evaluate('''() => {
                    const results = [];
                    const cards = Array.from(document.querySelectorAll('.match-item, .card-match, .item-match, [class*="match"], [class*="item"]'));
                    const targets = cards.length > 0 ? cards : Array.from(document.querySelectorAll('a[href*="/truc-tiep"], a[href*="/match"], a[href*="/live"], a[href*="-vs-"]')).map(a => a.closest('div') || a);

                    targets.forEach(card => {
                        const link = card.querySelector('a[href*="/truc-tiep"], a[href*="/match"], a[href*="/live"], a[href*="-vs-"]') || (card.tagName === 'A' ? card : null);
                        if (!link) return;
                        
                        const href = link.getAttribute('href');
                        if (!href) return;

                        // Tìm logo đội bóng (bỏ qua icon mặt trời / icon trang web)
                        let logo = '';
                        const teamImgs = Array.from(card.querySelectorAll('[class*="team"] img, [class*="club"] img, [class*="flag"] img, .logo-team img'));
                        if (teamImgs.length > 0) {
                            let src = teamImgs[0].getAttribute('src') || teamImgs[0].getAttribute('data-src') || '';
                            if (src) logo = src.startsWith('http') ? src : window.location.origin + src;
                        }

                        if (!logo) {
                            const allImgs = Array.from(card.querySelectorAll('img'));
                            for (let img of allImgs) {
                                let src = img.getAttribute('src') || img.getAttribute('data-src') || '';
                                let srcLower = src.toLowerCase();
                                if (src && !srcLower.includes('avatar') && !srcLower.includes('favicon') && 
                                    !srcLower.includes('banner') && !srcLower.includes('logo-site') && 
                                    !srcLower.includes('sun') && !srcLower.includes('icon-default') &&
                                    !srcLower.includes('thumb-default')) {
                                    logo = src.startsWith('http') ? src : window.location.origin + src;
                                    break;
                                }
                            }
                        }

                        results.push({
                            url: href.startsWith('http') ? href : window.location.origin + href,
                            text: card.innerText || link.innerText || '',
                            logo: logo
                        });
                    });
                    return results;
                }''')

                if raw_items:
                    active_domain = domain
                    print(f"[+] Lấy thành công {len(raw_items)} phần tử tại {domain}")
                    break
            except Exception as e:
                print(f"[-] Không thể kết nối {domain}: {e}")

        browser.close()

    for item in raw_items:
        text = item['text']
        if not text or is_invalid_text(text):
            continue

        # 1. Trích xuất giờ
        time_match = re.search(r'(\d{1,2}:\d{2})', text)
        m_time = time_match.group(1) if time_match else "LIVE"

        # 2. Trích xuất BLV (Chuẩn hóa chỉ giữ lại tên BLV)
        blv_name = ""
        blv_match = re.search(r'((?:BLV|Chuối|Gà|Bình luận viên)\s+[A-Za-zÀ-ỹ0-9]+(?:\s+[A-Za-zÀ-ỹ0-9]+)?)', text, re.IGNORECASE)
        if blv_match:
            raw_blv = clean_str(blv_match.group(1))
            for kw in TOURNAMENT_KEYWORDS + ["hls", "live", "trực tiếp"]:
                if kw in raw_blv.lower():
                    raw_blv = re.split(re.escape(kw), raw_blv, flags=re.IGNORECASE)[0].strip()
            blv_name = raw_blv

        # 3. Trích xuất Tên 2 đội bóng (Lọc sạch các cụm tên giải đấu dính vào)
        clean_text = re.sub(r'\d{1,2}:\d{2}', '', text)
        clean_text = re.sub(r'\d{1,2}/\d{1,2}', '', clean_text)

        teams_str = ""
        vs_match = re.search(r'([A-Za-zÀ-ỹ0-9\s\.\-]+)\s+(?:vs|-)\s+([A-Za-zÀ-ỹ0-9\s\.\-]+)', clean_text, re.IGNORECASE)
        if vs_match:
            t1 = clean_str(vs_match.group(1).split('\n')[-1])
            t2 = clean_str(vs_match.group(2).split('\n')[0])

            # Lọc bỏ từ khóa giải đấu ở 2 đầu tên đội
            for kw in TOURNAMENT_KEYWORDS:
                t1 = re.sub(r'(?i)^' + re.escape(kw) + r'\s*[-:\.]*\s*', '', t1).strip()
                t1 = re.sub(r'(?i)\s*[-:\.]*\s*' + re.escape(kw) + r'$', '', t1).strip()
                t2 = re.sub(r'(?i)^' + re.escape(kw) + r'\s*[-:\.]*\s*', '', t2).strip()
                t2 = re.sub(r'(?i)\s*[-:\.]*\s*' + re.escape(kw) + r'$', '', t2).strip()

            if len(t1) >= 2 and len(t2) >= 2 and not is_tournament(t1) and not is_tournament(t2):
                if not is_invalid_text(t1) and not is_invalid_text(t2):
                    teams_str = f"{t1} vs {t2}"

        if not teams_str:
            lines = [clean_str(l) for l in clean_text.split('\n') if len(clean_str(l)) >= 2]
            valid_lines = [l for l in lines if not any(kw in l.lower() for kw in FILTER_KEYWORDS) and not is_invalid_text(l) and not is_tournament(l)]
            if len(valid_lines) >= 2:
                teams_str = f"{valid_lines[0]} vs {valid_lines[1]}"

        if not teams_str or is_invalid_text(teams_str):
            continue

        blv_suffix = f" ({blv_name})" if blv_name else ""
        title = f"{m_time} {today_str} ⚽ {teams_str}{blv_suffix} [hls]"

        key = f"{item['url']}_{title}"
        if key not in seen_keys:
            seen_keys.add(key)
            parsed_matches.append({
                "title": title,
                "logo": item['logo'],
                "url": item['url']
            })

    # Ghi file playlist.m3u
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")
        if not parsed_matches:
            f.write(f'#EXTINF:-1 tvg-logo="{active_domain}/favicon.ico" group-title="{GROUP_NAME}",Chưa có trận đấu nào\n')
            f.write("http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4\n")
        else:
            for m in parsed_matches:
                logo_attr = f'tvg-logo="{m["logo"]}"' if m["logo"] else ''
                f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}",{m["title"]}\n')
                f.write(f'#EXTVLCOPT:http-referrer={active_domain}/\n')
                f.write(f'#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)\n')
                f.write(f'{m["url"]}|Referer={active_domain}/&User-Agent=Mozilla/5.0\n\n')

if __name__ == "__main__":
    run_scraper()
    
