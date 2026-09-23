import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

URLS_TO_TRY = [
    "https://chuoichientv1.link",
    "https://chuoichientv.link",
    "https://chuoichientv1.com"
]
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Chuối Chiến TV"

FILTER_KEYWORDS = [
    "cup", "cúp", "league", "championship", "asian games", "v-league", 
    "premier", "champions", "euro", "copa", "afc", "fifa", "uefa", 
    "serie", "liga", "bundesliga", "live", "trực tiếp", "hls", "flv"
]

def run_scraper():
    matches = []
    today_str = datetime.now().strftime("%d/%m")
    base_used = URLS_TO_TRY[0]

    try:
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
            for target_url in URLS_TO_TRY:
                try:
                    print(f"[*] Kết nối: {target_url}")
                    page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_timeout(4000)
                    
                    # Cuộn trang để tải full danh sách
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                    page.wait_for_timeout(1500)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(1500)

                    raw_items = page.evaluate('''() => {
                        const results = [];
                        const links = Array.from(document.querySelectorAll('a'));
                        links.forEach(a => {
                            const href = a.getAttribute('href') || '';
                            if (!href) return;

                            const isMatch = href.includes('/truc-tiep') || 
                                            href.includes('/match') || 
                                            href.includes('/live') || 
                                            href.includes('bong-da') || 
                                            href.includes('-vs-');
                            if (!isMatch) return;

                            const card = a.closest('.match-item, .item-match, .card-match, .match-card, div') || a;
                            
                            let logo = '';
                            const imgs = Array.from(card.querySelectorAll('img'));
                            for (let img of imgs) {
                                let src = img.getAttribute('src') || img.getAttribute('data-src') || '';
                                if (src && !src.includes('avatar') && !src.includes('favicon') && !src.includes('banner')) {
                                    logo = src.startsWith('http') ? src : window.location.origin + src;
                                    break;
                                }
                            }

                            results.push({
                                url: href.startsWith('http') ? href : window.location.origin + href,
                                text: card.innerText || a.innerText || '',
                                logo: logo
                            });
                        });
                        return results;
                    }''')

                    if raw_items:
                        base_used = target_url
                        print(f"[+] Tìm thấy {len(raw_items)} trận đấu.")
                        break
                except Exception as e:
                    print(f"[-] Lỗi truy cập {target_url}: {e}")

            # Xử lý & định dạng từng trận
            unique_keys = set()
            for item in raw_items:
                text = item['text']
                if not text or len(text.strip()) < 3:
                    continue

                # Lấy giờ
                time_match = re.search(r'(\d{1,2}:\d{2})', text)
                m_time = time_match.group(1) if time_match else "15:00"

                # Lấy BLV
                blv_name = ""
                blv_match = re.search(r'((?:BLV|Chuối|Gà)\s+[A-Za-zÀ-ỹ0-9\s\+]+)', text, re.IGNORECASE)
                if blv_match:
                    blv_name = blv_match.group(1).strip()
                    blv_name = re.split(r'(?:hls|flv|live|trực tiếp|\d{1,2}:\d{2})', blv_name, flags=re.IGNORECASE)[0].strip()

                # Lấy tên 2 đội
                clean_text = re.sub(r'\d{1,2}:\d{2}', '', text)
                teams_str = ""
                vs_match = re.search(r'([A-Za-zÀ-ỹ0-9\s\.\-]+)\s+(?:vs|-)\s+([A-Za-zÀ-ỹ0-9\s\.\-]+)', clean_text, re.IGNORECASE)
                if vs_match:
                    t1 = vs_match.group(1).split('\n')[-1].strip()
                    t2 = vs_match.group(2).split('\n')[0].strip()
                    if len(t1) >= 2 and len(t2) >= 2:
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
                title_formatted = f"{m_time} {today_str} ⚽ {teams_str}{blv_suffix} [hls]"

                dedup_key = f"{item['url']}_{title_formatted}"
                if dedup_key not in unique_keys:
                    unique_keys.add(dedup_key)
                    matches.append({
                        "title": title_formatted,
                        "logo": item['logo'],
                        "url": item['url']
                    })

            browser.close()
    except Exception as ex:
        print(f"[-] Lỗi chính: {ex}")

    # Ghi file M3U (đảm bảo luôn tạo file kể cả khi lỗi để không bị sập Actions)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")
        if not matches:
            f.write(f'#EXTINF:-1 tvg-logo="{base_used}/favicon.ico" group-title="{GROUP_NAME}",Chưa có trận đấu nào\n')
            f.write("http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4\n")
        else:
            for m in matches:
                logo_attr = f'tvg-logo="{m["logo"]}"' if m["logo"] else ''
                f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}",{m["title"]}\n')
                f.write(f'#EXTVLCOPT:http-referrer={base_used}/\n')
                f.write(f'#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)\n')
                f.write(f'{m["url"]}|Referer={base_used}/&User-Agent=Mozilla/5.0\n\n')

if __name__ == "__main__":
    run_scraper()
    
