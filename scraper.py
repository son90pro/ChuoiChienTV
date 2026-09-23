import re
import time
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

DOMAINS = [
    "https://chuoichien.tv",
    "https://bonglautv.pro",
    "https://chuoichientv1.link",
    "https://chuoichientv.com",
    "https://chuoichientv.live"
]

OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Chuối Chiến TV"

BLV_PATTERNS = [
    r'Chuối\s+[A-Za-zÀ-ỹ0-9]+',
    r'BLV\s+[A-Za-zÀ-ỹ0-9]+',
    r'Bình\s+luận\s+viên\s+[A-Za-zÀ-ỹ0-9]+'
]

BAD_IMG_KEYWORDS = [
    'sun', 'oca', 'asiad', 'asian', 'banner', 'favicon', 'avatar', 
    'logo-site', 'default', 'thumb', 'league', 'event', 'icon', 
    'widget', 'advertisement', 'bg', 'header', 'footer', 'tournament'
]

def clean_str(t):
    return re.sub(r'\s+', ' ', t or '').strip()

def parse_teams(text, url):
    """Trích xuất tên 2 đội thi đấu (Ưu tiên đọc từ URL slug - Chính xác 100%)"""
    try:
        path = url.split('?')[0].rstrip('/')
        slug = path.split('/')[-1]
        slug = re.sub(r'[-_]\d+$', '', slug)
        if '-vs-' in slug.lower():
            parts = re.split(r'-vs-', slug, flags=re.IGNORECASE)
            t1 = parts[0].replace('-', ' ').strip().title()
            t2 = parts[1].replace('-', ' ').strip().title()
            if len(t1) >= 2 and len(t2) >= 2:
                return f"{t1} vs {t2}"
    except Exception:
        pass

    clean = re.sub(r'\d{1,2}:\d{2}', '', text)
    clean = re.sub(r'\d{1,2}/\d{1,2}', '', clean)
    for pat in BLV_PATTERNS:
        clean = re.sub(pat, '', clean, flags=re.IGNORECASE)

    vs_match = re.search(r'([A-Za-zÀ-ỹ0-9\s\.\-]+)\s+(?:vs|-)\s+([A-Za-zÀ-ỹ0-9\s\.\-]+)', clean, re.IGNORECASE)
    if vs_match:
        t1 = clean_str(vs_match.group(1).split('\n')[-1])
        t2 = clean_str(vs_match.group(2).split('\n')[0])
        if len(t1) >= 2 and len(t2) >= 2 and "giúp bạn" not in t1.lower():
            return f"{t1} vs {t2}"

    return ""

def scrape_with_playwright():
    raw_items = []
    active_domain = DOMAINS[0]
    
    try:
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

            for domain in DOMAINS:
                try:
                    print(f"[*] [Playwright] Đang thử kết nối: {domain}")
                    page.goto(domain, timeout=20000, wait_until="domcontentloaded")
                    page.wait_for_timeout(2500)

                    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                    page.wait_for_timeout(1000)

                    items = page.evaluate('''() => {
                        const items = [];
                        const links = Array.from(document.querySelectorAll('a[href]'));

                        const BAD_IMG_KEYWORDS = [
                            'sun', 'oca', 'asiad', 'asian', 'banner', 'favicon', 'avatar', 
                            'logo-site', 'default', 'thumb', 'league', 'event', 'icon', 
                            'widget', 'advertisement', 'bg', 'header', 'footer', 'tournament'
                        ];

                        links.forEach(a => {
                            const href = a.getAttribute('href') || '';
                            if (!href) return;

                            const isMatch = href.includes('/truc-tiep') || 
                                            href.includes('/match') || 
                                            href.includes('/live') || 
                                            href.includes('-vs-') ||
                                            href.includes('bong-da');
                            if (!isMatch) return;

                            let card = a;
                            let curr = a.parentElement;
                            while (curr && curr.tagName !== 'BODY') {
                                const otherMatchLinks = curr.querySelectorAll('a[href*="/truc-tiep"], a[href*="/match"], a[href*="/live"], a[href*="-vs-"]');
                                if (otherMatchLinks.length > 1) break;
                                card = curr;
                                curr = curr.parentElement;
                            }

                            let logo = '';
                            const imgs = Array.from(card.querySelectorAll('img'));
                            for (let img of imgs) {
                                let src = img.getAttribute('data-src') || img.getAttribute('data-original') || img.getAttribute('src') || '';
                                let srcLower = src.toLowerCase();
                                if (src && !BAD_IMG_KEYWORDS.some(kw => srcLower.includes(kw))) {
                                    logo = src.startsWith('http') ? src : window.location.origin + src;
                                    break;
                                }
                            }

                            items.push({
                                url: href.startsWith('http') ? href : window.location.origin + href,
                                text: card.innerText || a.innerText || '',
                                logo: logo
                            });
                        });
                        return items;
                    }''')

                    if items and len(items) > 0:
                        raw_items = items
                        active_domain = domain
                        print(f"[+] Playwright lấy thành công {len(raw_items)} trận tại {domain}")
                        break
                except Exception as e:
                    print(f"[-] Playwright lỗi kết nối {domain}: {e}")

            browser.close()
    except Exception as e:
        print(f"[-] Lỗi Playwright: {e}")

    return raw_items, active_domain

def scrape_with_cloudscraper():
    """Dự phòng: Dùng Cloudscraper nếu Playwright bị Cloudflare chặn"""
    raw_items = []
    active_domain = DOMAINS[0]
    
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'android', 'desktop': False}
    )

    for domain in DOMAINS:
        try:
            print(f"[*] [Cloudscraper] Đang thử kết nối: {domain}")
            res = scraper.get(domain, timeout=15)
            if res.status_code == 200 and len(res.text) > 1000:
                soup = BeautifulSoup(res.text, 'html.parser')
                links = soup.find_all('a', href=True)
                for a in links:
                    href = a['href']
                    if any(k in href for k in ['/truc-tiep', '/match', '/live', '-vs-', 'bong-da']):
                        full_url = href if href.startswith('http') else domain.rstrip('/') + '/' + href.lstrip('/')
                        card = a.find_parent(['div', 'li']) or a
                        text = card.get_text(separator=' ', strip=True)
                        
                        logo = ""
                        imgs = card.find_all('img')
                        for img in imgs:
                            src = img.get('data-src') or img.get('src') or ""
                            src_lower = src.lower()
                            if src and not any(kw in src_lower for kw in BAD_IMG_KEYWORDS):
                                logo = src if src.startswith('http') else domain.rstrip('/') + '/' + src.lstrip('/')
                                break
                        
                        raw_items.append({
                            'url': full_url,
                            'text': text,
                            'logo': logo
                        })
                if raw_items:
                    active_domain = domain
                    print(f"[+] Cloudscraper lấy thành công {len(raw_items)} trận tại {domain}")
                    break
        except Exception as e:
            print(f"[-] Cloudscraper lỗi {domain}: {e}")

    return raw_items, active_domain

def run_scraper():
    today_str = datetime.now().strftime("%d/%m")
    
    # 1. Thử lấy bằng Playwright
    raw_items, active_domain = scrape_with_playwright()

    # 2. Nếu Playwright không ra trận nào, kích hoạt Cloudscraper ngay
    if not raw_items:
        print("[!] Playwright không lấy được dữ liệu, chuyển sang Cloudscraper...")
        raw_items, active_domain = scrape_with_cloudscraper()

    parsed_matches = []
    seen_urls = set()

    for item in raw_items:
        url = item['url']
        text = item['text']

        if url in seen_urls:
            continue

        blv_name = ""
        for pat in BLV_PATTERNS:
            m_blv = re.search(pat, text, re.IGNORECASE)
            if m_blv:
                blv_name = clean_str(m_blv.group(0))
                break

        time_match = re.search(r'(\d{1,2}:\d{2})', text)
        m_time = time_match.group(1) if time_match else "LIVE"

        teams_str = parse_teams(text, url)
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

    print(f"[*] TỔNG SỐ TRẬN ĐẤU CÀO THÀNH CÔNG: {len(parsed_matches)}")

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
                f.write(f'{m["url"]}|Referer={active_domain}/&User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)\n\n')

if __name__ == "__main__":
    run_scraper()
    
