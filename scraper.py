import time
import re
from urllib.parse import quote
from playwright.sync_api import sync_playwright

# Tên miền Cloudflare Worker của anh Sơn
WORKER_DOMAIN = "cctv.sonnguyen90pro.workers.dev"

# Danh sách tên miền dự phòng (tự động chuyển trang nếu bị Cloudflare chặn)
DOMAINS = [
    "https://chuoichientv.com",
    "https://gavang33.me",
    "https://chuoichien.tv",
    "https://gavang.tv"
]

OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Chuối Chiên TV"

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
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            extra_http_headers={
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"
            }
        )

        final_matches = []
        successful_base_url = ""

        # Lần lượt thử kết nối các tên miền dự phòng
        for domain in DOMAINS:
            page = context.new_page()
            try:
                print(f"[*] Đang thử kết nối: {domain}")
                page.goto(domain, timeout=25000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)

                # Kiểm tra xem có bị dính Cloudflare Challenge không
                title = page.title()
                if "Just a moment" in title or "Cloudflare" in title:
                    print(f"[!] Trang {domain} bị Cloudflare chặn, chuyển trang tiếp theo...")
                    page.close()
                    continue

                raw_matches = page.evaluate('''() => {
                    const matches = [];
                    const selectors = [
                        'a[href*="/truc-tiep/"]', 'a[href*="/match/"]', 
                        'a[href*="/xem/"]', 'a[href*="/live/"]',
                        '.match-item', '.card-match', '.item-match'
                    ];
                    
                    let elements = Array.from(document.querySelectorAll(selectors.join(',')));
                    
                    if (elements.length === 0) {
                        elements = Array.from(document.querySelectorAll('a')).filter(a => {
                            const text = a.innerText || '';
                            return text.toLowerCase().includes('vs') || (a.getAttribute('href') || '').includes('/truc-tiep');
                        });
                    }

                    elements.forEach(card => {
                        const linkEl = card.tagName === 'A' ? card : (card.querySelector('a') || card);
                        const href = linkEl.getAttribute('href');
                        if (!href || href === '#' || href.startsWith('javascript')) return;

                        let logo = '';
                        const img = card.querySelector('img');
                        if (img) {
                            logo = img.getAttribute('src') || img.getAttribute('data-src') || '';
                            if (logo && !logo.startsWith('http')) logo = window.location.origin + logo;
                        }

                        matches.push({
                            url: href.startsWith('http') ? href : window.location.origin + href,
                            text: card.innerText || '',
                            logo: logo
                        });
                    });

                    return matches;
                }''')

                if raw_matches and len(raw_matches) > 0:
                    print(f"[+] Lấy thành công {len(raw_matches)} liên kết trận đấu từ {domain}")
                    successful_base_url = domain

                    unique_matches = {}
                    for item in raw_matches:
                        url = item['url']
                        text = item['text']
                        if not text or url in unique_matches:
                            continue

                        time_match = re.search(r'(\d{1,2}:\d{2})', text)
                        date_match = re.search(r'(\d{1,2}/\d{1,2})', text)
                        m_time = time_match.group(1) if time_match else "LIVE"
                        m_date = date_match.group(1) if date_match else ""
                        time_str = f"{m_time} {m_date}".strip()

                        blv_match = re.search(r'\((?:Chuối|BLV|Gà)\s+[A-Za-zÀ-ỹ0-9\s]+\)', text, re.IGNORECASE) or re.search(r'(?:Chuối|BLV|Gà)\s+[A-Za-zÀ-ỹ0-9]+', text, re.IGNORECASE)
                        blv_str = f" ({blv_match.group(0).strip('()')})" if blv_match else ""

                        lines = [l.strip() for l in text.split('\n') if l.strip() and not re.search(r'\d{1,2}:\d{2}', l)]
                        title_clean = " ".join(lines[:2]) if lines else "Trận đấu Trực Tiếp"
                        title_clean = re.sub(r'\[hls\]|\[flv\]', '', title_clean, flags=re.IGNORECASE).strip()

                        full_title = f"{time_str} ⚽ {title_clean}{blv_str}"

                        unique_matches[url] = {
                            "title": full_title,
                            "logo": item['logo'],
                            "url": url
                        }

                    match_list = list(unique_matches.values())
                    page.close()

                    print(f"[*] Đã lọc được {len(match_list)} trận đấu. Đang quét lấy link m3u8...")
                    for idx, match in enumerate(match_list):
                        print(f"[{idx+1}/{len(match_list)}] Quét stream: {match['title']}")
                        m3u8_url = get_m3u8_for_match(context, match['url'])
                        match['m3u8_url'] = m3u8_url

                    final_matches = match_list
                    break
                else:
                    print(f"[-] Chưa cào được trận đấu tại {domain}")
                    page.close()

            except Exception as e:
                print(f"[!] Lỗi kết nối {domain}: {e}")
                page.close()

        browser.close()

    # Xuất ra file playlist.m3u
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

    print(f"[*] Hoàn tất! Đã xuất {len(final_matches)} trận đấu vào {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
