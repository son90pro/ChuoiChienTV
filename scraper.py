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

# CHỈ lọc bỏ các từ rác / quảng cáo (KHÔNG chặn U23, U20, Cup, Nữ...)
SPAM_KEYWORDS = [
    "giúp bạn", "toàn diện", "thế giới", "bản quyền", "hệ thống", 
    "trải nghiệm", "chất lượng", "miễn phí", "liên hệ", "đăng ký", 
    "khuyến mãi", "chuoichien", "bonglau", "soi kèo", "đặt cược", 
    "cam kết", "tải trang", "uy lực", "phát sóng"
]

BLV_PATTERNS = [
    r'Chuối\s+(?:Tây|Nhỏ|To|Kem|Lá|Lửa|Chín|Xanh|Đỏ|Siêu|Gà|Sơn|Nổ|Béo|Gáy|Ngố|Cả)',
    r'BLV\s+[A-Za-zÀ-ỹ0-9]+',
    r'Bình\s+luận\s+viên\s+[A-Za-zÀ-ỹ0-9]+'
]

def clean_str(t):
    return re.sub(r'\s+', ' ', t or '').strip()

def is_spam(text):
    t_lower = text.lower().strip()
    if len(t_lower) < 2 or "chuối" in t_lower or "blv" in t_lower:
        return True
    return any(kw in t_lower for kw in SPAM_KEYWORDS)

def run_scraper():
    today_str = datetime.now().strftime("%d/%m")
    parsed_matches = []
    seen_urls = set()
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

                # Cuộn trang nhiều lần để tải hết danh sách trận (Lazy load)
                for _ in range(3):
                    page.evaluate("window.scrollBy(0, 1000)")
                    page.wait_for_timeout(800)

                raw_items = page.evaluate('''() => {
                    const results = [];
                    const links = Array.from(document.querySelectorAll('a[href*="/truc-tiep"], a[href*="/match"], a[href*="/live"], a[href*="-vs-"]'));

                    links.forEach(link => {
                        const href = link.getAttribute('href');
                        if (!href) return;

                        let card = link.closest('.match-item, .card-match, .item-match, .item, .card, div[class*="match"]') || link;

                        let logo = '';
                        const teamImgs = Array.from(card.querySelectorAll('[class*="team"] img, [class*="club"] img, [class*="flag"] img, .logo-team img, img'));
                        for (let img of teamImgs) {
                            let src = img.getAttribute('src') || img.getAttribute('data-src') || '';
                            let srcLower = src.toLowerCase();
                            if (src && !srcLower.includes('avatar') && !srcLower.includes('favicon') && 
                                !srcLower.includes('banner') && !srcLower.includes('logo-site') && 
                                !srcLower.includes('sun') && !srcLower.includes('icon-default')) {
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
                print(f"[-] Không thể kết nối {domain}: {e}")

        browser.close()

    for item in raw_items:
        url = item['url']
        text = item['text']

        if url in seen_urls:
            continue

        # 1. Trích xuất tên BLV
        blv_name = ""
        for pat in BLV_PATTERNS:
            m_blv = re.search(pat, text, re.IGNORECASE)
            if m_blv:
                blv_name = clean_str(m_blv.group(0))
                break

        # 2. Xóa BLV khỏi văn bản
        text_clean = text
        if blv_name:
            text_clean = re.sub(re.escape(blv_name), '', text_clean, flags=re.IGNORECASE)

        # 3. Trích xuất giờ
        time_match = re.search(r'(\d{1,2}:\d{2})', text)
        m_time = time_match.group(1) if time_match else "LIVE"

        # 4. Trích xuất Tên 2 đội bóng
        clean_text = re.sub(r'\d{1,2}:\d{2}', '', text_clean)
        clean_text = re.sub(r'\d{1,2}/\d{1,2}', '', clean_text)

        teams_str = ""
        vs_match = re.search(r'([A-Za-zÀ-ỹ0-9\s\.\-]+)\s+(?:vs|-)\s+([A-Za-zÀ-ỹ0-9\s\.\-]+)', clean_text, re.IGNORECASE)
        if vs_match:
            t1 = clean_str(vs_match.group(1).split('\n')[-1])
            t2 = clean_str(vs_match.group(2).split('\n')[0])
            if not is_spam(t1) and not is_spam(t2) and len(t1) >= 2 and len(t2) >= 2:
                teams_str = f"{t1} vs {t2}"

        # Nếu không tìm thấy cặp vs bằng chữ, lấy tên 2 đội trực tiếp từ link URL slug
        if not teams_str and '-vs-' in url:
            try:
                slug = url.split('/')[-1].split('?')[0]
                slug = re.sub(r'-\d+$', '', slug)
                parts = slug.split('-vs-')
                t1 = parts[0].replace('-', ' ').title()
                t2 = parts[1].replace('-', ' ').title()
                teams_str = f"{t1} vs {t2}"
            except:
                pass

        if not teams_str:
            continue

        blv_suffix = f" ({blv_name})" if blv_name else ""
        title = f"{m_time} {today_str} ⚽ {teams_str}{blv_suffix} [hls]"

        seen_urls.add(url)
        parsed_matches.append({
            "title": title,
            "logo": item['logo'],
            "url": url
        })

    print(f"[*] Tổng số trận thu thập được: {len(parsed_matches)}")

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
    
