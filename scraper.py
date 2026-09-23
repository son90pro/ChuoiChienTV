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

BLV_PATTERNS = [
    r'Chuối\s+[A-Za-zÀ-ỹ0-9]+',
    r'BLV\s+[A-Za-zÀ-ỹ0-9]+',
    r'Bình\s+luận\s+viên\s+[A-Za-zÀ-ỹ0-9]+'
]

def clean_str(t):
    return re.sub(r'\s+', ' ', t or '').strip()

def parse_teams(text, url):
    try:
        slug = url.split('?')[0].rstrip('/').split('/')[-1]
        slug = re.sub(r'-\d+$', '', slug)
        if '-vs-' in slug.lower():
            parts = re.split(r'-vs-', slug, flags=re.IGNORECASE)
            t1 = parts[0].replace('-', ' ').strip().title()
            t2 = parts[1].replace('-', ' ').strip().title()
            if len(t1) >= 2 and len(t2) >= 2:
                return f"{t1} vs {t2}"
    except:
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
                print(f"[*] Đang kết nối trang chủ: {domain}")
                page.goto(domain, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                page.wait_for_timeout(1000)

                raw_items = page.evaluate('''() => {
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

                if len(raw_items) > 0:
                    active_domain = domain
                    print(f"[+] Lấy thành công {len(raw_items)} trận đấu tại {domain}")
                    break
            except Exception as e:
                print(f"[-] Không thể kết nối {domain}: {e}")

        # TRÍCH XUẤT LINK TRÌNH PHÁT VIDEO THỰC TẾ (IFRAME PLAYER)
        for item in raw_items:
            url = item['url']
            text = item['text']

            if url in seen_urls:
                continue

            # Bóc tách tên BLV
            blv_name = ""
            for pat in BLV_PATTERNS:
                m_blv = re.search(pat, text, re.IGNORECASE)
                if m_blv:
                    blv_name = clean_str(m_blv.group(0))
                    break

            # Bóc tách Giờ
            time_match = re.search(r'(\d{1,2}:\d{2})', text)
            m_time = time_match.group(1) if time_match else "LIVE"

            # Bóc tách Tên 2 đội
            teams_str = parse_teams(text, url)
            if not teams_str:
                continue

            # Bấm vào trang chi tiết trận đấu để lấy link luồng video iframe player
            stream_url = url
            try:
                print(f"[*] Bóc tách luồng video: {teams_str}")
                page.goto(url, timeout=15000, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)

                iframe_src = page.evaluate('''() => {
                    const iframe = document.querySelector('iframe[src*="embed"], iframe[src*="player"], iframe[src*="stream"], iframe[src*="live"], iframe');
                    return iframe ? iframe.getAttribute('src') : '';
                }''')

                if iframe_src:
                    stream_url = iframe_src if iframe_src.startsWith('http') else active_domain.rstrip('/') + '/' + iframe_src.lstrip('/')
            except Exception as err:
                print(f"[-] Dùng link trang chính cho {teams_str}: {err}")

            blv_suffix = f" ({blv_name})" if blv_name else ""
            title = f"{m_time} {today_str} ⚽ {teams_str}{blv_suffix} [hls]"

            seen_urls.add(url)
            parsed_matches.append({
                "title": title,
                "logo": item['logo'],
                "url": stream_url
            })

        browser.close()

    print(f"[*] Tổng số luồng phát đã hoàn tất: {len(parsed_matches)}")

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
    
