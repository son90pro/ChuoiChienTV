import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

# Danh sách tên miền chính và dự phòng của Chuối Chiến TV
DOMAINS = [
    "https://chuoichien.tv",
    "https://bonglautv.pro",
    "https://chuoichientv1.link",
    "https://chuoichientv.com"
]

OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Chuối Chiến TV"

# 1. Từ khóa khẩu hiệu/quảng cáo CẤM LẤY (Loại bỏ triệt để văn xuôi giới thiệu web)
SLOGAN_KEYWORDS = [
    "giúp bạn", "toàn diện", "thế giới", "bản quyền", "hệ thống", 
    "trải nghiệm", "chất lượng", "miễn phí", "liên hệ", "đăng ký", 
    "khuyến mãi", "chuoichien", "bonglau", "người xem", "phát sóng",
    "uy lực", "soi kèo", "đặt cược", "tốc độ", "tải trang", "cam kết",
    "chúng tôi", "đam mê", "vươn mình", "chuẩn mực"
]

# 2. Từ khóa hệ thống/giải đấu
FILTER_KEYWORDS = [
    "cup", "cúp", "league", "championship", "asian games", "v-league", 
    "premier", "champions", "euro", "copa", "afc", "fifa", "uefa", 
    "serie", "liga", "bundesliga", "live", "trực tiếp", "hls", "flv", "xem ngay"
]

def is_invalid_text(text):
    t_lower = text.lower()
    # Nếu chứa từ khóa khẩu hiệu -> Bỏ qua
    if any(kw in t_lower for kw in SLOGAN_KEYWORDS):
        return True
    return False

def clean_str(t):
    return re.sub(r'\s+', ' ', t or '').strip()

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
            viewport={"width": 1280, "height": 720}
        )
        page = context.new_page()

        raw_items = []
        for domain in DOMAINS:
            try:
                print(f"[*] Đang thử kết nối: {domain}")
                page.goto(domain, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)

                # Cuộn trang để kích hoạt nạp danh sách trận đấu
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                page.wait_for_timeout(1000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500)

                # Quét DOM tìm thẻ trận đấu
                raw_items = page.evaluate('''() => {
                    const results = [];
                    // Ưu tiên tìm các thẻ chứa trận đấu
                    const cards = Array.from(document.querySelectorAll('.match-item, .card-match, .item-match, [class*="match"], [class*="item"]'));
                    const targets = cards.length > 0 ? cards : Array.from(document.querySelectorAll('a[href*="/truc-tiep"], a[href*="/match"], a[href*="/live"], a[href*="-vs-"]')).map(a => a.closest('div') || a);

                    targets.forEach(card => {
                        const link = card.querySelector('a[href*="/truc-tiep"], a[href*="/match"], a[href*="/live"], a[href*="-vs-"]') || (card.tagName === 'A' ? card : null);
                        if (!link) return;
                        
                        const href = link.getAttribute('href');
                        if (!href) return;

                        let logo = '';
                        const imgs = Array.from(card.querySelectorAll('img'));
                        for (let img of imgs) {
                            let src = img.getAttribute('src') || img.getAttribute('data-src') || '';
                            if (src && !src.includes('avatar') && !src.includes('favicon') && !src.includes('banner') && !src.includes('logo-site')) {
                                logo = src.startsWith('http') ? src : window.location.origin + src;
                                break;
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
                print(f"[-] Không thể truy cập {domain}: {e}")

        browser.close()

    # Bóc tách và kiểm tra kỹ lưỡng từng trận đấu
    for item in raw_items:
        text = item['text']
        if not text or is_invalid_text(text):
            continue

        # 1. Trích xuất giờ
        time_match = re.search(r'(\d{1,2}:\d{2})', text)
        m_time = time_match.group(1) if time_match else "LIVE"

        # 2. Trích xuất BLV
        blv_name = ""
        blv_match = re.search(r'((?:BLV|Chuối|Gà|Bình luận viên)\s+[A-Za-zÀ-ỹ0-9\s\+]+)', text, re.IGNORECASE)
        if blv_match:
            blv_name = clean_str(blv_match.group(1))
            blv_name = re.split(r'(?:hls|flv|live|trực tiếp|\d{1,2}:\d{2})', blv_name, flags=re.IGNORECASE)[0].strip()

        # 3. Trích xuất Tên 2 đội (BẮT BỘC PHẢI CÓ DẠNG "ĐỘI A vs ĐỘI B")
        clean_text = re.sub(r'\d{1,2}:\d{2}', '', text)
        clean_text = re.sub(r'\d{1,2}/\d{1,2}', '', clean_text)

        teams_str = ""
        vs_match = re.search(r'([A-Za-zÀ-ỹ0-9\s\.\-]+)\s+(?:vs|-)\s+([A-Za-zÀ-ỹ0-9\s\.\-]+)', clean_text, re.IGNORECASE)
        if vs_match:
            t1 = clean_str(vs_match.group(1).split('\n')[-1])
            t2 = clean_str(vs_match.group(2).split('\n')[0])
            
            # Kiểm tra tên đội không phải câu slogan dài
            if len(t1) >= 2 and len(t2) >= 2 and not t1.isdigit() and not t2.isdigit():
                if not is_invalid_text(t1) and not is_invalid_text(t2):
                    teams_str = f"{t1} vs {t2}"

        # Bỏ qua nếu không trích xuất được cặp đấu chuẩn
        if not teams_str:
            lines = [clean_str(l) for l in clean_text.split('\n') if len(clean_str(l)) >= 2]
            valid_lines = [l for l in lines if not any(kw in l.lower() for kw in FILTER_KEYWORDS) and not is_invalid_text(l)]
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

    print(f"\n[*] Tổng số trận đấu trích xuất chuẩn: {len(parsed_matches)}")

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
    
