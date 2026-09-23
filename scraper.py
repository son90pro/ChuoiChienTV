import re
import time
from datetime import datetime
import cloudscraper
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# Danh sách các tên miền chính & dự phòng của Chuối Chiến TV
DOMAINS = [
    "https://chuoichientv1.link",
    "https://chuoichientv.live",
    "https://chuoichien.tv",
    "https://chuoichientv.com"
]

OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Chuối Chiến TV"

FILTER_KEYWORDS = [
    "cup", "cúp", "league", "championship", "asian games", "v-league", 
    "premier", "champions", "euro", "copa", "afc", "fifa", "uefa", 
    "serie", "liga", "bundesliga", "live", "trực tiếp", "hls", "flv", "xem ngay"
]

def clean_str(t):
    return re.sub(r'\s+', ' ', t or '').strip()

def scrape_with_cloudscraper(url):
    print(f"[*] Thử cào bằng Cloudscraper: {url}")
    results = []
    try:
        scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'android', 'mobile': True}
        )
        res = scraper.get(url, timeout=15)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            links = soup.find_all('a', href=True)
            for a in links:
                href = a['href']
                if any(k in href for k in ['/truc-tiep', '/match', '/live', '-vs-']):
                    container = a.find_parent(['div', 'li']) or a
                    text = container.get_text(separator=' ', strip=True)
                    
                    img = container.find('img')
                    logo = ""
                    if img:
                        src = img.get('src') or img.get('data-src') or ""
                        if src and not any(x in src for x in ['avatar', 'favicon', 'site']):
                            logo = src if src.startswith('http') else url.rstrip('/') + '/' + src.lstrip('/')
                    
                    full_url = href if href.startswith('http') else url.rstrip('/') + '/' + href.lstrip('/')
                    results.append({'url': full_url, 'text': text, 'logo': logo})
    except Exception as e:
        print(f"[-] Lỗi Cloudscraper: {e}")
    return results

def scrape_with_playwright(url):
    print(f"[*] Thử cào bằng Playwright: {url}")
    results = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36",
                viewport={"width": 412, "height": 915}
            )
            page = context.new_page()
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            page.wait_for_timeout(1000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)

            results = page.evaluate('''() => {
                const items = [];
                const links = Array.from(document.querySelectorAll('a'));
                
                links.forEach(a => {
                    const href = a.getAttribute('href') || '';
                    if (!href) return;
                    
                    const isMatch = href.includes('/truc-tiep') || 
                                    href.includes('/match') || 
                                    href.includes('/live') || 
                                    href.includes('xem') || 
                                    href.includes('-vs-');
                    if (!isMatch) return;

                    const container = a.closest('div[class*="match"], div[class*="item"], div[class*="card"], li') || a.parentElement || a;
                    const text = container.innerText || a.innerText || '';
                    
                    let logo = '';
                    const imgs = Array.from(container.querySelectorAll('img'));
                    for (let img of imgs) {
                        let src = img.getAttribute('src') || img.getAttribute('data-src') || '';
                        if (src && !src.includes('avatar') && !src.includes('favicon') && !src.includes('logo-site')) {
                            logo = src.startsWith('http') ? src : window.location.origin + src;
                            break;
                        }
                    }

                    items.push({
                        url: href.startsWith('http') ? href : window.location.origin + href,
                        text: text,
                        logo: logo
                    });
                });
                return items;
            }''')
            browser.close()
    except Exception as e:
        print(f"[-] Lỗi Playwright: {e}")
    return results

def run():
    today_str = datetime.now().strftime("%d/%m")
    raw_items = []
    active_domain = DOMAINS[0]

    for domain in DOMAINS:
        print(f"\n==========================================")
        print(f"Đang kiểm tra: {domain}")
        
        # Thử 1: Cloudscraper (Bypass Cloudflare)
        raw_items = scrape_with_cloudscraper(domain)
        if raw_items:
            active_domain = domain
            print(f"[+] Thành công với Cloudscraper! Lấy được {len(raw_items)} liên kết.")
            break
            
        # Thử 2: Playwright Giả lập Android
        raw_items = scrape_with_playwright(domain)
        if raw_items:
            active_domain = domain
            print(f"[+] Thành công với Playwright! Lấy được {len(raw_items)} liên kết.")
            break

    parsed_matches = []
    seen_keys = set()

    for item in raw_items:
        text = item['text']
        if not text or len(text.strip()) < 3:
            continue

        # 1. Bóc giờ
        time_match = re.search(r'(\d{1,2}:\d{2})', text)
        m_time = time_match.group(1) if time_match else "LIVE"

        # 2. Bóc BLV
        blv_name = ""
        blv_match = re.search(r'((?:BLV|Chuối|Gà|Bình luận viên)\s+[A-Za-zÀ-ỹ0-9\s\+]+)', text, re.IGNORECASE)
        if blv_match:
            blv_name = blv_match.group(1).strip()
            blv_name = re.split(r'(?:hls|flv|live|trực tiếp|\d{1,2}:\d{2})', blv_name, flags=re.IGNORECASE)[0].strip()

        # 3. Bóc tên 2 đội bóng
        clean_text = re.sub(r'\d{1,2}:\d{2}', '', text)
        clean_text = re.sub(r'\d{1,2}/\d{1,2}', '', clean_text)

        teams_str = ""
        vs_match = re.search(r'([A-Za-zÀ-ỹ0-9\s\.\-]+)\s+(?:vs|-)\s+([A-Za-zÀ-ỹ0-9\s\.\-]+)', clean_text, re.IGNORECASE)
        if vs_match:
            t1 = clean_str(vs_match.group(1).split('\n')[-1])
            t2 = clean_str(vs_match.group(2).split('\n')[0])
            if len(t1) >= 2 and len(t2) >= 2 and not t1.isdigit() and not t2.isdigit():
                teams_str = f"{t1} vs {t2}"

        if not teams_str:
            lines = [l.strip() for l in clean_text.split('\n') if len(l.strip()) >= 2]
            valid = [l for l in lines if not any(kw in l.lower() for kw in FILTER_KEYWORDS)]
            if len(valid) >= 2:
                teams_str = f"{valid[0]} vs {valid[1]}"
            elif len(valid) == 1:
                teams_str = valid[0]

        if not teams_str:
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

    print(f"\n[*] Tổng số trận đấu trích xuất thành công: {len(parsed_matches)}")

    # Ghi xuất file playlist.m3u
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")
        if not parsed_matches:
            print("[-] Không cào được trận nào. Ghi file m3u thông báo dự phòng.")
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
    run()
    
