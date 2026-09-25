import time
import re
import sys
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

BASE_URL = "https://live07.chuoichientv.me"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Chuối Chiên TV"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

LOGOS = {
    "manchester": "https://flagcdn.com/w320/gb-eng.png", "mu": "https://flagcdn.com/w320/gb-eng.png",
    "netherlands": "https://flagcdn.com/w320/nl.png", "hà lan": "https://flagcdn.com/w320/nl.png",
    "germany": "https://flagcdn.com/w320/de.png", "đức": "https://flagcdn.com/w320/de.png",
    "spain": "https://flagcdn.com/w320/es.png", "tây ban nha": "https://flagcdn.com/w320/es.png",
    "france": "https://flagcdn.com/w320/fr.png", "pháp": "https://flagcdn.com/w320/fr.png",
    "italy": "https://flagcdn.com/w320/it.png", "ý": "https://flagcdn.com/w320/it.png",
    "portugal": "https://flagcdn.com/w320/pt.png", "bồ đào nha": "https://flagcdn.com/w320/pt.png",
    "england": "https://flagcdn.com/w320/gb-eng.png", "anh": "https://flagcdn.com/w320/gb-eng.png",
    "slovakia": "https://flagcdn.com/w320/sk.png", "turkiye": "https://flagcdn.com/w320/tr.png", 
    "thổ nhĩ kỳ": "https://flagcdn.com/w320/tr.png", "belgium": "https://flagcdn.com/w320/be.png", 
    "bỉ": "https://flagcdn.com/w320/be.png", "vietnam": "https://flagcdn.com/w320/vn.png", 
    "việt nam": "https://flagcdn.com/w320/vn.png", "thailand": "https://flagcdn.com/w320/th.png", 
    "indonesia": "https://flagcdn.com/w320/id.png", "japan": "https://flagcdn.com/w320/jp.png", 
    "south korea": "https://flagcdn.com/w320/kr.png", "hàn quốc": "https://flagcdn.com/w320/kr.png",
    "brazil": "https://flagcdn.com/w320/br.png", "argentina": "https://flagcdn.com/w320/ar.png"
}

def get_team_logo(teams_str: str) -> str:
    t_lower = teams_str.lower()
    for key, url in LOGOS.items():
        if key in t_lower:
            return url
    return "https://flagcdn.com/w320/un.png"

def extract_match_details(context, match_url):
    """
    Truy cập thẳng vào trang trận đấu.
    1. Đọc chính xác Tên trận từ thẻ <title> của trình duyệt.
    2. Nghe lén Network để lấy Link m3u8 VÀ Header Referer thực tế của máy chủ video.
    """
    page = context.new_page()
    page.route("**/*.{png,jpg,jpeg,svg,css,woff,woff2}", lambda route: route.abort())
    
    stream_info = {"url": "", "referer": BASE_URL + "/"}
    
    def handle_request(req):
        u = req.url
        # Bắt link m3u8 thực tế
        if (".m3u8" in u or ".flv" in u) and "blob:" not in u:
            if not stream_info["url"]:
                stream_info["url"] = u
                # Bắt Referer cực kỳ quan trọng để TiviMate không bị chặn
                stream_info["referer"] = req.headers.get("referer", BASE_URL + "/")

    page.on("request", handle_request)
    
    title_text = ""
    try:
        page.goto(match_url, timeout=20000, wait_until="domcontentloaded")
        title_text = page.title()
        
        # Thử bấm Play để kích hoạt luồng video
        for selector in ["iframe", "video", ".play-btn", "button", ".vjs-big-play-button"]:
            try:
                el = page.locator(selector).first
                if el:
                    el.click(timeout=800)
                    time.sleep(0.5)
            except:
                continue

        # Chờ tối đa 8 giây để bắt link m3u8
        for _ in range(16):
            if stream_info["url"]:
                break
            time.sleep(0.5)
            
    except Exception as e:
        pass
    finally:
        page.close()

    return title_text, stream_info

def run_scraper():
    vn_tz = timezone(timedelta(hours=7))
    today_str = datetime.now(vn_tz).strftime("%d/%m")
    parsed_items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context(user_agent=USER_AGENT, timezone_id="Asia/Ho_Chi_Minh")
        
        # BƯỚC 1: Lấy toàn bộ link trận đấu từ trang chủ
        page = context.new_page()
        page.goto(BASE_URL, timeout=30000, wait_until="domcontentloaded")
        time.sleep(2)
        
        links = page.evaluate('''() => {
            const urls = new Set();
            document.querySelectorAll('a[href*="/truc-tiep/"], a[href*="/match/"]').forEach(a => {
                const href = a.getAttribute('href');
                if(href) urls.add(href.startsWith('http') ? href : window.location.origin + href);
            });
            return Array.from(urls);
        }''')
        page.close()
        
        print(f"[*] Tìm thấy {len(links)} link trận. Bắt đầu quét chi tiết từng trận...")

        # BƯỚC 2: Vào từng trang để bóc tách chính xác 100%
        for url in links:
            title_text, stream_info = extract_match_details(context, url)
            if not title_text:
                continue

            # Bóc tách tên đội bóng từ Title (VD: "Trực tiếp Nam Định vs Lee Man...")
            teams_title = "Trận đấu Trực Tiếp"
            vs_match = re.search(r'([A-Za-zÀ-ỹ0-9\s]+)\s+vs\s+([A-Za-zÀ-ỹ0-9\s]+)', title_text, re.I)
            if vs_match:
                teams_title = f"{vs_match.group(1).strip()} vs {vs_match.group(2).strip()}"
                # Dọn dẹp các từ thừa
                teams_title = re.sub(r'(Trực tiếp|Xem|Bóng đá|Hôm nay)', '', teams_title, flags=re.I).strip()
            
            # Bóc tách BLV
            blv_name = "Chuối Chiên"
            blv_match = re.search(r'(?:BLV|Caster)[:\-\s]*([A-Za-zÀ-ỹ\s]+)', title_text, re.I)
            if blv_match:
                blv_name = blv_match.group(1).split('|')[0].split('-')[0].strip()
            else:
                for b in ["Trốc Tru", "Chuối Nhỏ", "Chuối Chao", "Chuối Lá", "Chuối Ngao", "Chuối Sấy"]:
                    if b.lower() in title_text.lower() or b.lower().replace(' ', '-') in url.lower():
                        blv_name = b
                        break

            # Bóc tách giờ
            time_match = re.search(r'\b(2[0-3]|[0-1]?\d)[:h](\d{2})\b', title_text, re.I)
            extracted_time = f"{time_match.group(1).zfill(2)}:{time_match.group(2)}" if time_match else "19:00"

            final_logo = get_team_logo(teams_title)
            playable_stream = stream_info["url"] if stream_info["url"] else url
            is_live = bool(stream_info["url"])
            stream_type = "[hls]" if ".m3u8" in playable_stream else "[flv]"

            full_title = f"{extracted_time} {today_str} ⚽ {teams_title} ({blv_name}) [FHD] {stream_type}"

            try:
                d, m = map(int, today_str.split('/'))
                h, mins = map(int, extracted_time.split(':'))
                dt_obj = datetime(datetime.now(vn_tz).year, m, d, h, mins, tzinfo=vn_tz)
            except:
                dt_obj = datetime(2099, 1, 1, 0, 0, tzinfo=vn_tz)

            parsed_items.append({
                "title": full_title,
                "logo": final_logo,
                "stream_url": playable_stream,
                "referer": stream_info["referer"],
                "is_live": is_live,
                "dt": dt_obj,
                "url": url
            })

        parsed_items.sort(key=lambda x: (x['dt'].date(), not x['is_live'], x['dt'].time()))
        browser.close()

    # BƯỚC 3: Ghi file M3U chuẩn TiviMate
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write('#EXTM3U\n\n')
        for item in parsed_items:
            f.write(f'#EXTINF:-1 tvg-logo="{item["logo"]}" group-title="{GROUP_NAME}" , {item["title"]} \n')
            
            # Gỡ bỏ hoàn toàn Worker proxy. Truyền trực tiếp Referer vào đuôi link để TiviMate tự xử lý
            if item["stream_url"].endswith(".m3u8") or item["stream_url"].endswith(".flv"):
                f.write(f'#EXTVLCOPT:http-referrer={item["referer"]}\n')
                f.write(f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n')
                f.write(f'{item["stream_url"]}|Referer={item["referer"]}&User-Agent={USER_AGENT}\n\n')
            else:
                f.write(f'{item["stream_url"]}\n\n')

    print(f"[*] Đã xuất thành công {len(parsed_items)} trận.")

if __name__ == "__main__":
    run_scraper()
    
