import time
import re
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

BASE_URL = "https://phalang.live"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Phá Làng TV"
REFERRER_HEADER = "https://phalang.live/"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Bộ tra cứu cờ quốc gia nét HD dự phòng
FLAG_LOGOS = {
    "japan": "https://flagcdn.com/w320/jp.png",
    "nhật bản": "https://flagcdn.com/w320/jp.png",
    "uruguay": "https://flagcdn.com/w320/uy.png",
    "laos": "https://flagcdn.com/w320/la.png",
    "lào": "https://flagcdn.com/w320/la.png",
    "brunei": "https://flagcdn.com/w320/bn.png",
    "south korea": "https://flagcdn.com/w320/kr.png",
    "hàn quốc": "https://flagcdn.com/w320/kr.png",
    "korea": "https://flagcdn.com/w320/kr.png",
    "ecuador": "https://flagcdn.com/w320/ec.png",
    "myanmar": "https://flagcdn.com/w320/mm.png",
    "timor": "https://flagcdn.com/w320/tl.png",
    "uzbekistan": "https://flagcdn.com/w320/uz.png",
    "iran": "https://flagcdn.com/w320/ir.png",
    "uae": "https://flagcdn.com/w320/ae.png",
    "yemen": "https://flagcdn.com/w320/ye.png",
    "vietnam": "https://flagcdn.com/w320/vn.png",
    "việt nam": "https://flagcdn.com/w320/vn.png",
    "thailand": "https://flagcdn.com/w320/th.png",
    "thái lan": "https://flagcdn.com/w320/th.png",
    "indonesia": "https://flagcdn.com/w320/id.png",
    "malaysia": "https://flagcdn.com/w320/my.png",
    "china": "https://flagcdn.com/w320/cn.png",
    "trung quốc": "https://flagcdn.com/w320/cn.png",
    "australia": "https://flagcdn.com/w320/au.png",
    "úc": "https://flagcdn.com/w320/au.png",
    "brazil": "https://flagcdn.com/w320/br.png"
}

def clean_slug_team_name(name_slug: str) -> str:
    """Xử lý tên đội từ URL slug an toàn không bị mất chữ"""
    if not name_slug:
        return ""
    # Loại bỏ tiền tố BLV hoặc GÀ
    s = re.sub(r'^(?:blv-)?ga-(?:sieu-)?[a-z0-9]+-', '', name_slug, flags=re.I)
    # Loại bỏ các mã ngẫu nhiên dính ở đuôi (ví dụ 2y8m4zhv0177qio)
    s = re.sub(r'-(?:luc|ngay|[a-z0-9]{8,}).*$', '', s, flags=re.I)
    s = s.replace('-', ' ').strip().title()
    return s

def process_logo_url(raw_logo: str, team1_name: str) -> str:
    """Chuẩn hóa Logo thành đường dẫn tuyệt đối chuẩn cho TiviMate"""
    if raw_logo and not raw_logo.startswith("data:image"):
        if raw_logo.startswith("//"):
            return "https:" + raw_logo
        elif raw_logo.startswith("http"):
            return raw_logo
        elif raw_logo.startswith("/"):
            return urljoin(BASE_URL, raw_logo)
    
    # Nếu logo web bị trống hoặc hỏng, lấy Cờ quốc gia HD
    t_lower = team1_name.lower().strip()
    for k, v in FLAG_LOGOS.items():
        if k in t_lower:
            return v
    return "https://flagcdn.com/w320/un.png"

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
            print(f"[*] Đang tải trang chủ: {BASE_URL}")
            page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
            time.sleep(3)

            # Cuộn trang từ từ để tải toàn bộ danh sách trận đấu (kể cả các trận sắp diễn ra)
            print("[*] Đang cuộn trang lấy danh sách trận phát & sắp diễn ra...")
            for _ in range(8):
                page.evaluate("window.scrollBy(0, 1200)")
                time.sleep(0.4)

            # Cào chi tiết thông tin các thẻ trận đấu từ DOM
            raw_cards = page.evaluate('''() => {
                const results = [];
                // Bắt tất cả liên kết trận đấu
                const cards = document.querySelectorAll('a[href*="/truc-tiep/"], a[href*="/match/"], a[href*="/live/"], a[href*="/tran/"], a[href*="/chi-tiet/"]');
                const seenUrls = new Set();

                cards.forEach(card => {
                    const href = card.getAttribute('href');
                    if (!href) return;
                    const fullUrl = href.startsWith('http') ? href : window.location.origin + href;
                    if (seenUrls.has(fullUrl)) return;
                    seenUrls.add(fullUrl);

                    // Lấy logo
                    let logo = '';
                    const imgs = card.querySelectorAll('img');
                    imgs.forEach(img => {
                        const src = img.src || img.getAttribute('data-src') || img.getAttribute('data-original') || '';
                        if (src && !logo && !src.includes('data:image')) {
                            logo = src;
                        }
                    });

                    // Lấy tên 2 đội từ thẻ văn bản nếu có
                    let domTeam1 = '', domTeam2 = '';
                    const teamNameEls = card.querySelectorAll('.team-name, .name, .team, span[class*="team"]');
                    if (teamNameEls.length >= 2) {
                        domTeam1 = teamNameEls[0].innerText.trim();
                        domTeam2 = teamNameEls[1].innerText.trim();
                    }

                    const text = card.innerText || card.parentElement.innerText || '';

                    results.push({
                        url: fullUrl,
                        logo: logo,
                        domTeam1: domTeam1,
                        domTeam2: domTeam2,
                        rawText: text
                    });
                });
                return results;
            }''')

            print(f"[*] Tìm thấy tổng cộng {len(raw_cards)} trận đấu. Đang trích xuất luồng...")

            for item in raw_cards:
                match_url = item['url']
                raw_logo = item['logo']
                card_text = item['rawText']
                dom_t1 = item['domTeam1']
                dom_t2 = item['domTeam2']

                # 1. Xác định Tên 2 đội bóng
                team1_name = ""
                teams_title = ""
                if dom_t1 and dom_t2:
                    team1_name = dom_t1.title()
                    teams_title = f"{team1_name} vs {dom_t2.title()}"
                else:
                    slug_match = re.search(r'/(?:truc-tiep|match|live|tran-dau|tran)/([^/?#]+)', match_url)
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
                    teams_title = "Trận đấu Trực Tiếp"

                # 2. Xử lý Logo chuẩn
                final_logo = process_logo_url(raw_logo, team1_name)

                # 3. Trạng thái, Thời gian & BLV
                status_icon = "🟢 " if any(k in card_text.lower() for k in ["trực tiếp", "live", "đang diễn ra"]) else "🟡 "
                
                time_match = re.search(r'(\d{1,2}[:h]\d{2})\s*(\d{1,2}/\d{1,2})?', card_text)
                time_str = ""
                if time_match:
                    t_val = time_match.group(1).replace('h', ':')
                    d_val = f" {time_match.group(2)}" if time_match.group(2) else ""
                    time_str = f"{t_val}{d_val} "

                blv_match = re.search(r'\(([^)]*(?:BLV|LÝ|GÀ)[^)]*)\)|\b((?:LÝ|BLV|GA)\s+[A-Za-zÀ-ỹ0-9\s]+)', card_text, re.I)
                blv_str = ""
                if blv_match:
                    found_blv = blv_match.group(1) or blv_match.group(2)
                    found_blv = re.sub(r'[a-zA-Z0-9]{8,}', '', found_blv).strip()
                    if found_blv:
                        blv_str = f" ({found_blv})"

                base_title = f"{status_icon}{time_str}⚽ {teams_title}{blv_str}".strip()

                # 4. Mở trang con bóc tách luồng .m3u8 (Bắt cả Luồng Mạng & Luồng Mã Nguồn)
                detail_page = context.new_page()
                m3u8_captured = []

                def handle_req(req):
                    u = req.url
                    if ".m3u8" in u and "blob:" not in u and u not in m3u8_captured:
                        m3u8_captured.append(u)

                detail_page.on("request", handle_req)

                try:
                    detail_page.goto(match_url, timeout=12000, wait_until="domcontentloaded")
                    time.sleep(2)
                    
                    # Quét bổ sung trong mã nguồn HTML cho các trận sắp diễn ra chưa chạy video
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

                # Nếu tìm thấy luồng .m3u8, đưa vào playlist
                if m3u8_captured:
                    for stream_url in m3u8_captured:
                        if "pull.digitalcdn.net" in stream_url:
                            matches_list.append({
                                "title": f"{base_title} [geo]",
                                "logo": final_logo,
                                "url": stream_url
                            })
                            # Tự động tạo luồng HD2
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
            print(f"[!] Lỗi khi cào dữ liệu: {e}")
        finally:
            browser.close()

    # 5. Xuất file M3U
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")

        for item in matches_list:
            logo_attr = f'tvg-logo="{item["logo"]}"' if item["logo"] else ''
            
            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}" , {item["title"]}\n')
            f.write(f'#EXTVLCOPT:http-referrer={REFERRER_HEADER}\n')
            f.write(f'{item["url"]}\n\n')

    print(f"[*] Đã xuất thành công {len(matches_list)} kênh vào {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
