import time
import re
import json
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

BASE_URL = "https://phalang.live"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Phá Làng TV"
REFERRER_HEADER = "https://phalang.live/"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Bộ sưu tập cờ quốc gia nét HD làm dự phòng khi logo trang web bị thiếu/lỗi
FLAG_LOGOS = {
    "japan": "https://flagcdn.com/w320/jp.png",
    "uruguay": "https://flagcdn.com/w320/uy.png",
    "laos": "https://flagcdn.com/w320/la.png",
    "brunei": "https://flagcdn.com/w320/bn.png",
    "south korea": "https://flagcdn.com/w320/kr.png",
    "korea": "https://flagcdn.com/w320/kr.png",
    "ecuador": "https://flagcdn.com/w320/ec.png",
    "myanmar": "https://flagcdn.com/w320/mm.png",
    "timor": "https://flagcdn.com/w320/tl.png",
    "uzbekistan": "https://flagcdn.com/w320/uz.png",
    "iran": "https://flagcdn.com/w320/ir.png",
    "uae": "https://flagcdn.com/w320/ae.png",
    "united arab emirates": "https://flagcdn.com/w320/ae.png",
    "yemen": "https://flagcdn.com/w320/ye.png",
    "vietnam": "https://flagcdn.com/w320/vn.png",
    "thailand": "https://flagcdn.com/w320/th.png",
    "indonesia": "https://flagcdn.com/w320/id.png",
    "malaysia": "https://flagcdn.com/w320/my.png",
    "china": "https://flagcdn.com/w320/cn.png",
    "australia": "https://flagcdn.com/w320/au.png",
    "brazil": "https://flagcdn.com/w320/br.png",
    "qatar": "https://flagcdn.com/w320/qa.png",
    "netherlands": "https://flagcdn.com/w320/nl.png",
    "germany": "https://flagcdn.com/w320/de.png",
    "norway": "https://flagcdn.com/w320/no.png",
    "denmark": "https://flagcdn.com/w320/dk.png",
    "portugal": "https://flagcdn.com/w320/pt.png",
    "wales": "https://flagcdn.com/w320/gb-wls.png",
    "philippines": "https://flagcdn.com/w320/ph.png",
    "singapore": "https://flagcdn.com/w320/sg.png",
    "georgia": "https://flagcdn.com/w320/ge.png"
}

def clean_hash_and_junk(text: str) -> str:
    """Xóa triệt để các mã ID ngẫu nhiên dính vào tên đội/BLV (ví dụ: 2Y8M4Zhv0177QIO)"""
    if not text:
        return ""
    # Xóa chuỗi gồm chữ và số ngẫu nhiên
    text = re.sub(r'\b(?=.*[0-9])(?=.*[a-zA-Z])[a-zA-Z0-9]{6,}\b', '', text)
    text = re.sub(r'[a-zA-Z0-9]{10,35}', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def get_best_logo(team_name: str, raw_logo_url: str) -> str:
    """Chuẩn hóa URL logo từ web hoặc tự động lấy cờ quốc gia nét HD"""
    if raw_logo_url and raw_logo_url.startswith("http"):
        return raw_logo_url
    if raw_logo_url and raw_logo_url.startswith("//"):
        return "https:" + raw_logo_url
    if raw_logo_url and raw_logo_url.startswith("/"):
        return urljoin(BASE_URL, raw_logo_url)
    
    t_lower = team_name.lower().strip()
    for key, url in FLAG_LOGOS.items():
        if key in t_lower:
            return url
    return "https://flagcdn.com/w320/un.png"

def parse_teams_and_blv(match_url: str, raw_text: str):
    """Trích xuất sạch tên 2 đội bóng và tên BLV"""
    cleaned_text = clean_hash_and_junk(raw_text)
    
    # 1. Tách tên BLV
    blv_str = ""
    blv_match = re.search(r'\(([^)]*(?:BLV|LÝ|GÀ)[^)]*)\)|\b((?:LÝ|BLV|GA)\s+[A-Za-zÀ-ỹ0-9\s]+)', cleaned_text, re.I)
    if blv_match:
        found_blv = blv_match.group(1) or blv_match.group(2)
        blv_str = f" ({clean_hash_and_junk(found_blv)})"

    # 2. Tách tên trận đấu từ URL Slug
    teams_str = ""
    team1_name = ""
    slug_match = re.search(r'/(?:truc-tiep|match|live)/([^/?#]+)', match_url)
    if slug_match:
        slug = slug_match.group(1)
        parts = slug.split('-vs-')
        if len(parts) == 2:
            t1_slug = re.sub(r'^(?:blv-)?ga-(?:sieu-)?[a-z0-9]+-', '', parts[0], flags=re.I)
            t2_slug = re.sub(r'-(?:luc|ngay|2y8m|318).*$', '', parts[1], flags=re.I)
            
            t1 = clean_hash_and_junk(t1_slug.replace('-', ' ')).title()
            t2 = clean_hash_and_junk(t2_slug.replace('-', ' ')).title()
            
            if t1 and t2:
                teams_str = f"{t1} vs {t2}"
                team1_name = t1

    if not teams_str:
        teams_str = "Trận đấu Trực Tiếp"

    # 3. Trạng thái & Thời gian
    status_icon = ""
    if "trực tiếp" in raw_text.lower() or "live" in raw_text.lower() or "đang diễn ra" in raw_text.lower():
        status_icon = "🟢 "
    elif "sắp diễn ra" in raw_text.lower():
        status_icon = "🟡 "

    time_match = re.search(r'(\d{1,2}[:h]\d{2})\s*(\d{1,2}/\d{1,2})?', raw_text)
    time_str = ""
    if time_match:
        t_val = time_match.group(1).replace('h', ':')
        d_val = f" {time_match.group(2)}" if time_match.group(2) else ""
        time_str = f"{t_val}{d_val} "

    return status_icon, time_str, teams_str, blv_str, team1_name

def run_scraper():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 10000},
            timezone_id="Asia/Ho_Chi_Minh",
            locale="vi-VN"
        )
        page = context.new_page()

        matches_list = []

        try:
            print(f"[*] Đang mở trang chủ: {BASE_URL}")
            page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
            time.sleep(3)

            # Cuộn trang để kích hoạt tải toàn bộ danh sách trận đấu
            for _ in range(5):
                page.evaluate("window.scrollBy(0, 1500)")
                time.sleep(0.5)

            # Cào tất cả thẻ trận đấu
            raw_cards = page.evaluate('''() => {
                const results = [];
                const cards = document.querySelectorAll('a[href*="/truc-tiep/"], a[href*="/match/"], a[href*="/live/"]');
                const seenUrls = new Set();

                cards.forEach(card => {
                    const href = card.getAttribute('href');
                    if (!href) return;
                    const fullUrl = href.startsWith('http') ? href : window.location.origin + href;
                    if (seenUrls.has(fullUrl)) return;
                    seenUrls.add(fullUrl);

                    let logo = '';
                    const img = card.querySelector('img');
                    if (img) {
                        logo = img.src || img.getAttribute('data-src') || img.getAttribute('data-original') || '';
                    }

                    const text = card.innerText || card.parentElement.innerText || '';

                    results.push({
                        url: fullUrl,
                        logo: logo,
                        text: text
                    });
                });
                return results;
            }''')

            print(f"[*] Tìm thấy {len(raw_cards)} trận đấu. Bắt đầu lấy luồng...")

            for idx, item in enumerate(raw_cards):
                match_url = item['url']
                raw_logo = item['logo']
                raw_text = item['text']

                status_icon, time_str, teams_str, blv_str, team1_name = parse_teams_and_blv(match_url, raw_text)
                final_logo = get_best_logo(team1_name, raw_logo)

                detail_page = context.new_page()
                m3u8_captured = []

                def handle_req(req):
                    u = req.url
                    if ".m3u8" in u and "blob:" not in u:
                        if u not in m3u8_captured:
                            m3u8_captured.append(u)

                detail_page.on("request", handle_req)

                try:
                    detail_page.goto(match_url, timeout=12000, wait_until="domcontentloaded")
                    time.sleep(2)
                except Exception:
                    pass
                finally:
                    detail_page.close()

                base_title = f"{status_icon}{time_str}⚽ {teams_str}{blv_str}".strip()

                if m3u8_captured:
                    for stream_url in m3u8_captured:
                        if "pull.digitalcdn.net" in stream_url:
                            # Luồng HD1
                            matches_list.append({
                                "title": f"{base_title} [geo]",
                                "logo": final_logo,
                                "url": stream_url
                            })
                            # Tự động tạo thêm luồng HD2
                            hd2_url = stream_url.replace("pull.digitalcdn.net", "pull1.digitalcdn.net")
                            matches_list.append({
                                "title": f"{base_title} (HD2) [geo]",
                                "logo": final_logo,
                                "url": hd2_url
                            })
                        elif "pull1.digitalcdn.net" in stream_url:
                            matches_list.append({
                                "title": f"{base_title} (HD2) [geo]",
                                "logo": final_logo,
                                "url": stream_url
                            })
                        else:
                            sub_tag = " (Nhà đài)" if "lilive" in stream_url or "eu.cc" in stream_url else ""
                            matches_list.append({
                                "title": f"{base_title}{sub_tag}",
                                "logo": final_logo,
                                "url": stream_url
                            })

        except Exception as e:
            print(f"[!] Lỗi: {e}")
        finally:
            browser.close()

    # Xuất file M3U ĐÚNG CHUẨN MẪU
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")

        for item in matches_list:
            logo_attr = f'tvg-logo="{item["logo"]}"' if item["logo"] else ''
            
            # Xuất link M3U nguyên bản tuyệt đối
            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}" , {item["title"]}\n')
            f.write(f'#EXTVLCOPT:http-referrer={REFERRER_HEADER}\n')
            f.write(f'{item["url"]}\n\n')

    print(f"[*] Đã xuất thành công {len(matches_list)} kênh vào {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
