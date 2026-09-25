import time
import re
from datetime import datetime
from urllib.parse import urljoin, quote
from playwright.sync_api import sync_playwright

# Domain mới nhất theo giao diện web hiện tại
BASE_URL = "https://phalang.tv"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Phá Làng TV"
REFERRER_HEADER = "https://phalang.tv/"
WORKER_DOMAIN = "chuoi-chien-iptv.sonnguyen90pro.workers.dev"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Bảng tra cứu cờ quốc gia chuẩn HD
FLAG_LOGOS = {
    "china": "https://flagcdn.com/w320/cn.png",
    "trung quốc": "https://flagcdn.com/w320/cn.png",
    "vietnam": "https://flagcdn.com/w320/vn.png",
    "việt nam": "https://flagcdn.com/w320/vn.png",
    "bangladesh": "https://flagcdn.com/w320/bd.png",
    "malaysia": "https://flagcdn.com/w320/my.png",
    "australia": "https://flagcdn.com/w320/au.png",
    "úc": "https://flagcdn.com/w320/au.png",
    "brazil": "https://flagcdn.com/w320/br.png",
    "japan": "https://flagcdn.com/w320/jp.png",
    "nhật bản": "https://flagcdn.com/w320/jp.png",
    "philippines": "https://flagcdn.com/w320/ph.png",
    "thailand": "https://flagcdn.com/w320/th.png",
    "thái lan": "https://flagcdn.com/w320/th.png",
    "indonesia": "https://flagcdn.com/w320/id.png",
    "south korea": "https://flagcdn.com/w320/kr.png",
    "hàn quốc": "https://flagcdn.com/w320/kr.png"
}

def clean_slug_team_name(name_slug: str) -> str:
    """Xử lý tên đội từ URL slug an toàn không bị mất chữ"""
    if not name_slug:
        return ""
    s = re.sub(r'^(?:blv-)?ga-(?:sieu-)?[a-z0-9]+-', '', name_slug, flags=re.I)
    s = re.sub(r'-(?:luc|ngay|[a-z0-9]{8,}).*$', '', s, flags=re.I)
    s = s.replace('-', ' ').strip().title()
    return s

def process_logo_url(raw_logo: str, team1_name: str) -> str:
    """Chuẩn hóa Logo thành đường dẫn tuyệt đối cho TiviMate"""
    if raw_logo and not raw_logo.startswith("data:image"):
        if raw_logo.startswith("//"):
            return "https:" + raw_logo
        elif raw_logo.startswith("http"):
            return raw_logo
        elif raw_logo.startswith("/"):
            return urljoin(BASE_URL, raw_logo)
    
    t_lower = team1_name.lower().strip()
    for k, v in FLAG_LOGOS.items():
        if k in t_lower:
            return v
    return "https://flagcdn.com/w320/un.png"

def run_scraper():
    today_str = datetime.now().strftime("%d/%m")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 3000},
            timezone_id="Asia/Ho_Chi_Minh",
            locale="vi-VN"
        )
        page = context.new_page()
        matches_list = []

        try:
            print(f"[*] Đang tải trang chủ Phá Làng TV: {BASE_URL}")
            page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
            time.sleep(3)

            # Cuộn trang nạp toàn bộ danh sách trận đấu
            print("[*] Cuộn trang lấy toàn bộ trận đấu...")
            for _ in range(5):
                page.evaluate("window.scrollBy(0, 800)")
                time.sleep(0.5)

            # Trích xuất danh sách các trận từ DOM trang phalang.tv
            raw_cards = page.evaluate('''() => {
                const results = [];
                // Bắt tất cả liên kết trận đấu
                const selector = 'a[href*="/truc-tiep/"], a[href*="/xem-truc-tiep/"], a[href*="/match/"], a[href*="/live/"], a[href*="/tran/"], a[href*="/chi-tiet/"], a[href*="/room/"]';
                const cards = document.querySelectorAll(selector);
                const seenUrls = new Set();

                cards.forEach(card => {
                    const href = card.getAttribute('href');
                    if (!href) return;
                    const fullUrl = href.startsWith('http') ? href : window.location.origin + href;
                    if (seenUrls.has(fullUrl)) return;
                    seenUrls.add(fullUrl);

                    let logo = '';
                    const imgs = card.querySelectorAll('img');
                    imgs.forEach(img => {
                        const src = img.src || img.getAttribute('data-src') || img.getAttribute('data-original') || '';
                        if (src && !logo && !src.includes('data:image')) {
                            logo = src;
                        }
                    });

                    // Lấy text hiển thị trong khung trận đấu
                    const parent = card.closest('div') || card;
                    const cardText = parent.innerText || card.innerText || '';

                    results.push({
                        url: fullUrl,
                        logo: logo,
                        rawText: cardText
                    });
                });
                return results;
            }''')

            print(f"[*] Tìm thấy tổng cộng {len(raw_cards)} trận đấu trên web. Đang xử lý...")

            for item in raw_cards:
                match_url = item['url']
                raw_logo = item['logo']
                card_text = item['rawText']

                # 1. Trích xuất Tên 2 đội từ URL slug hoặc Văn bản
                team1_name = ""
                teams_title = ""
                slug_match = re.search(r'/(?:truc-tiep|xem-truc-tiep|match|live|tran|room)/([^/?#]+)', match_url)
                if slug_match:
                    slug = slug_match.group(1)
                    if "-vs-" in slug:
                        parts = slug.split('-vs-')
                        t1 = clean_slug_team_name(parts[0])
                        t2 = clean_slug_team_name(parts[1])
                        if t1 and t2:
                            team1_name = t1
                            teams_title = f"{t1} vs {t2}"

                if not teams_title:
                    # Bóc tách tên đội từ văn bản nếu slug không hỗ trợ
                    lines = [l.strip() for l in card_text.split('\n') if l.strip()]
                    team_lines = [l for l in lines if not re.search(r'(\d{1,2}:\d{2}|sắp diễn ra|trực tiếp|live)', l, re.I)]
                    if len(team_lines) >= 2:
                        team1_name = team_lines[0]
                        teams_title = f"{team_lines[0]} vs {team_lines[1]}"
                    else:
                        teams_title = "Trận đấu Trực Tiếp"

                final_logo = process_logo_url(raw_logo, team1_name)

                # 2. Xử lý Trạng thái & Thời gian
                is_live = any(k in card_text.lower() for k in ["trực tiếp", "live", "đang diễn ra", "hiệp"])
                status_icon = "🟢 " if is_live else "🟡 "
                
                time_match = re.search(r'(\d{1,2}[:h]\d{2})\s*(\d{1,2}/\d{1,2})?', card_text)
                time_str = ""
                if time_match:
                    t_val = time_match.group(1).replace('h', ':')
                    d_val = f" {time_match.group(2)}" if time_match.group(2) else f" {today_str}"
                    time_str = f"{t_val}{d_val} "

                # 3. BLV
                blv_match = re.search(r'((?:Phá Làng|BLV|Caster|Gà)\s+[A-Za-zÀ-ỹ0-9\s]+)', card_text, re.I)
                blv_str = ""
                if blv_match:
                    found_blv = blv_match.group(1).strip()
                    blv_str = f" ({found_blv})"

                base_title = f"{status_icon}{time_str}⚽ {teams_title}{blv_str}".strip()

                # 4. Mở trang con tìm luồng video m3u8
                detail_page = context.new_page()
                m3u8_captured = []

                def handle_req(req):
                    u = req.url
                    if ".m3u8" in u and "blob:" not in u and u not in m3u8_captured:
                        m3u8_captured.append(u)

                detail_page.on("request", handle_req)

                try:
                    detail_page.goto(match_url, timeout=10000, wait_until="domcontentloaded")
                    time.sleep(1.5)
                    
                    if not m3u8_captured:
                        html_content = detail_page.content()
                        found_m3u8 = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html_content)
                        for f_url in found_m3u8:
                            if "blob:" not in f_url and f_url not in m3u8_captured:
                                m3u8_captured.append(f_url)
                except Exception:
                    pass
                finally:
                    detail_page.close()

                # 5. Đưa trận đấu vào Playlist (Bao gồm cả trận SẮP DIỄN RA)
                if m3u8_captured:
                    for stream_url in m3u8_captured:
                        matches_list.append({
                            "title": base_title,
                            "logo": final_logo,
                            "url": f"https://{WORKER_DOMAIN}/proxy?url={quote(stream_url, safe='')}"
                        })
                else:
                    # TRẬN SẮP DIỄN RA: Vẫn giữ lại trong playlist với đường dẫn proxy Worker
                    fallback_proxy = f"https://{WORKER_DOMAIN}/live?url={quote(match_url, safe='')}"
                    matches_list.append({
                        "title": f"{base_title} (Sắp diễn ra)",
                        "logo": final_logo,
                        "url": fallback_proxy
                    })

        except Exception as e:
            print(f"[!] Lỗi khi cào dữ liệu: {e}")
        finally:
            browser.close()

    # 6. Ghi file M3U Playlist
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")

        for item in matches_list:
            logo_attr = f'tvg-logo="{item["logo"]}"' if item["logo"] else ''
            
            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}",{item["title"]}\n')
            f.write(f'#EXTVLCOPT:http-referrer={REFERRER_HEADER}\n')
            f.write(f'{item["url"]}\n\n')

    print(f"[*] Đã xuất thành công {len(matches_list)} trận vào {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
  
