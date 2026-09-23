import time
import re
from urllib.parse import quote
from playwright.sync_api import sync_playwright

WORKER_DOMAIN = "cctv.sonnguyen90pro.workers.dev"

DOMAINS = [
    "https://chuoichientv.com",
    "https://gavang33.me",
    "https://chuoichien.tv",
    "https://gavang.tv"
]

OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Chuối Chiên TV"

# Các từ ngữ trạng thái cần loại bỏ khi tìm tên trận đấu
NOISE_PATTERNS = [
    r'hiệp\s*\d', r'h1', r'h2', r'đang diễn ra', r'trực tiếp', r'phút\s*\d*', 
    r'ft', r'ht', r'full time', r'half time', r'xem ngay', r'sắp diễn ra', r'live', r'\[hls\]', r'\[flv\]'
]

def clean_noise(text):
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    return text.strip()

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
        successful_base_url = ""

        for domain in DOMAINS:
            page = context.new_page()
            try:
                print(f"[*] Thử kết nối: {domain}")
                page.goto(domain, timeout=25000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)

                if "Just a moment" in page.title() or "Cloudflare" in page.title():
                    page.close()
                    continue

                raw_matches = page.evaluate('''() => {
                    const matches = [];
                    const cards = Array.from(document.querySelectorAll('.match-item, .card-match, .item-match, div[class*="match"], a[href*="/truc-tiep/"], a[href*="/match/"]'));

                    cards.forEach(card => {
                        const linkEl = card.tagName === 'A' ? card : (card.querySelector('a[href*="/truc-tiep/"], a[href*="/match/"], a[href*="/xem/"]') || card.querySelector('a'));
                        if (!linkEl) return;

                        const href = linkEl.getAttribute('href');
                        if (!href || href === '#' || href.startsWith('javascript')) return;

                        // Tìm logo đội bóng
                        let logo = '';
                        const imgs = card.querySelectorAll('img');
                        for (let img of imgs) {
                            let src = img.getAttribute('src') || img.getAttribute('data-src') || '';
                            if (src && !src.includes('avatar') && !src.includes('favicon') && !src.includes('icon')) {
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

                if raw_matches and len(raw_matches) > 0:
                    successful_base_url = domain
                    unique_matches = {}

                    for item in raw_matches:
                        url = item['url']
                        text = item['fullText']
                        if not text or url in unique_matches:
                            continue

                        # 1. Trích xuất thời gian
                        time_match = re.search(r'(\d{1,2}:\d{2})', text)
                        date_match = re.search(r'(\d{1,2}/\d{1,2})', text)
                        m_time = time_match.group(1) if time_match else "LIVE"
                        m_date = date_match.group(1) if date_match else ""
                        time_str = f"{m_time} {m_date}".strip()

                        # 2. Trích xuất tên BLV
                        blv_str = ""
                        blv_match = re.search(r'\((Chuối\s+[A-Za-zÀ-ỹ0-9\s]+)\)', text, re.IGNORECASE) or re.search(r'(Chuối\s+[A-Za-zÀ-ỹ0-9]+)', text, re.IGNORECASE)
                        if blv_match:
                            blv_name = blv_match.group(1) if '(' in blv_match.group(0) else blv_match.group(0)
                            blv_str = f" ({blv_name.strip()})"

                        # 3. Lọc lấy tên hai đội bóng (Ưu tiên tìm cấu trúc Team A vs Team B)
                        clean_text = clean_noise(text)
                        teams_str = ""
                        
                        vs_match = re.search(r'([A-Za-zÀ-ỹ0-9\s\.\-]+)\s+(?:vs|-)\s+([A-Za-zÀ-ỹ0-9\s\.\-]+)', clean_text, re.IGNORECASE)
                        if vs_match:
                            t1 = vs_match.group(1).split('\n')[-1].strip()
                            t2 = vs_match.group(2).split('\n')[0].strip()
                            if len(t1) >= 2 and len(t2) >= 2:
                                teams_str = f"{t1} vs {t2}"

                        if not teams_str:
                            lines = [l.strip() for l in clean_text.split('\n') if l.strip() and not re.search(r'\d{1,2}:\d{2}', l)]
                            if len(lines) >= 2:
                                teams_str = f"{lines[0]} vs {lines[1]}"
                            elif len(lines) == 1:
                                teams_str = lines[0]
                            else:
                                teams_str = "Trận đấu Trực Tiếp"

                        full_title = f"{time_str} ⚽ {teams_str}{blv_str}"

                        unique_matches[url] = {
                            "title": full_title,
                            "logo": item['logo'],
                            "url": url
                        }

                    match_list = list(unique_matches.values())
                    page.close()

                    print(f"[*] Tìm thấy {len(match_list)} trận. Bắt đầu lấy link video m3u8...")
                    for idx, match in enumerate(match_list):
                        print(f"[{idx+1}/{len(match_list)}] Lấy link: {match['title']}")
                        m3u8_url = get_m3u8_for_match(context, match['url'])
                        match['m3u8_url'] = m3u8_url

                    final_matches = match_list
                    break
                else:
                    page.close()

            except Exception as e:
                print(f"[!] Lỗi {domain}: {e}")
                page.close()

        browser.close()

    # Xuất file playlist.m3u
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")

        for item in final_matches:
            logo_attr = f'tvg-logo="{item["logo"]}"' if item["logo"] else ''
            ref_url = successful_base_url if successful_base_url else "https://chuoichientv.com"

            if item.get('m3u8_url'):
                encoded_m3u8 = quote(item['m3u8_url'], safe='')
                encoded_ref = quote(ref_url + '/', safe='')
                stream_url = f"https://{WORKER_DOMAIN}/proxy?url={encoded_m3u8}&referer={encoded_ref}"
            else:
                stream_url = f"https://{WORKER_DOMAIN}/live?url={quote(item['url'], safe='')}"
            
            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}",{item["title"]}\n')
            f.write(f'{stream_url}\n\n')

    print(f"[*] Hoàn tất xuất file {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
