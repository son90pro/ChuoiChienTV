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

# Từ khóa cấm xuất hiện trong tên đội bóng (giải đấu, môn thể thao, từ ngữ hệ thống)
INVALID_TEAM_KEYWORDS = [
    "bóng chuyền", "bóng rổ", "bóng đá", "vô địch", "châu âu", "châu á", 
    "world cup", "asian games", "emperor's cup", "emperor", "jfa", "championship",
    "v-league", "premier league", "champions league", "euro", "copa", "afc", "fifa",
    "uefa", "serie", "liga", "bundesliga", "u20", "u23", "u19", "u17", "women", "nữ",
    "cúp", "cup", "giải", "bảng", "vòng", "trực tiếp", "live", "hls", "flv", "xem ngay",
    "giúp bạn", "toàn diện", "thế giới", "bản quyền", "hệ thống", "trải nghiệm",
    "soi kèo", "đặt cược", "cam kết"
]

# Pattern nhận diện tên các BLV Chuối Chiến để loại bỏ hoàn toàn trước khi bắt tên đội
BLV_PATTERNS = [
    r'Chuối\s+(?:Tây|Nhỏ|To|Kem|Lá|Lửa|Chín|Xanh|Đỏ|Siêu|Gà|Sơn|Nổ|Béo|Gáy|Ngố|Cả)',
    r'BLV\s+[A-Za-zÀ-ỹ0-9]+',
    r'Bình\s+luận\s+viên\s+[A-Za-zÀ-ỹ0-9]+'
]

def clean_str(t):
    return re.sub(r'\s+', ' ', t or '').strip()

def is_invalid_team(name):
    n_lower = name.lower().strip()
    if len(n_lower) < 2:
        return True
    # Tên đội tuyệt đối KHÔNG chứa từ "chuối" hoặc "blv"
    if "chuối" in n_lower or "blv" in n_lower:
        return True
    # Không dính các từ khóa giải đấu/môn thể thao
    if any(kw in n_lower for kw in INVALID_TEAM_KEYWORDS):
        return True
    return False

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
        if not text or len(text.strip()) < 3:
            continue

        # 1. Trích xuất tên BLV
        blv_name = ""
        for pat in BLV_PATTERNS:
            m_blv = re.search(pat, text, re.IGNORECASE)
            if m_blv:
                blv_name = clean_str(m_blv.group(0))
                break

        # 2. XÓA SẠCH tên BLV khỏi văn bản trước khi trích xuất tên đội bóng
        text_clean = text
        if blv_name:
            text_clean = re.sub(re.escape(blv_name), '', text_clean, flags=re.IGNORECASE)
        for pat in BLV_PATTERNS:
            text_clean = re.sub(pat, '', text_clean, flags=re.IGNORECASE)

        # 3. Trích xuất giờ
        time_match = re.search(r'(\d{1,2}:\d{2})', text)
        m_time = time_match.group(1) if time_match else "LIVE"

        # 4. Làm sạch thời gian & ngày tháng
        clean_text = re.sub(r'\d{1,2}:\d{2}', '', text_clean)
        clean_text = re.sub(r'\d{1,2}/\d{1,2}', '', clean_text)

        # 5. Trích xuất Tên 2 đội bóng
        teams_str = ""
        vs_match = re.search(r'([A-Za-zÀ-ỹ0-9\s\.\-]+)\s+(?:vs|-)\s+([A-Za-zÀ-ỹ0-9\s\.\-]+)', clean_text, re.IGNORECASE)
        if vs_match:
            t1 = clean_str(vs_match.group(1).split('\n')[-1])
            t2 = clean_str(vs_match.group(2).split('\n')[0])

            # Loại bỏ các từ khóa giải đấu ở 2 đầu tên đội
            for kw in INVALID_TEAM_KEYWORDS:
                t1 = re.sub(r'(?i)^' + re.escape(kw) + r'\s*[-:\.]*\s*', '', t1).strip()
                t1 = re.sub(r'(?i)\s*[-:\.]*\s*' + re.escape(kw) + r'$', '', t1).strip()
                t2 = re.sub(r'(?i)^' + re.escape(kw) + r'\s*[-:\.]*\s*', '', t2).strip()
                t2 = re.sub(r'(?i)\s*[-:\.]*\s*' + re.escape(kw) + r'$', '', t2).strip()

            if not is_invalid_team(t1) and not is_invalid_team(t2):
                teams_str = f"{t1} vs {t2}"

        if not teams_str:
            lines = [clean_str(l) for l in clean_text.split('\n') if len(clean_str(l)) >= 2]
            valid_lines = [l for l in lines if not is_invalid_team(l)]
            if len(valid_lines) >= 2:
                teams_str = f"{valid_lines[0]} vs {valid_lines[1]}"

        if not teams_str or is_invalid_team(teams_str):
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
    
