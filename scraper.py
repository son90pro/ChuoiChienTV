import time
import re
import json
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

BASE_URL = "https://live07.chuoichientv.me"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Chuối Chiên TV"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Bảng tra cứu cờ quốc gia / Logo
LOGOS = {
    "netherlands": "https://flagcdn.com/w320/nl.png", "hà lan": "https://flagcdn.com/w320/nl.png",
    "germany": "https://flagcdn.com/w320/de.png", "đức": "https://flagcdn.com/w320/de.png",
    "spain": "https://flagcdn.com/w320/es.png", "tây ban nha": "https://flagcdn.com/w320/es.png",
    "france": "https://flagcdn.com/w320/fr.png", "pháp": "https://flagcdn.com/w320/fr.png",
    "italy": "https://flagcdn.com/w320/it.png", "ý": "https://flagcdn.com/w320/it.png",
    "portugal": "https://flagcdn.com/w320/pt.png", "bồ đào nha": "https://flagcdn.com/w320/pt.png",
    "england": "https://flagcdn.com/w320/gb-eng.png", "anh": "https://flagcdn.com/w320/gb-eng.png",
    "slovakia": "https://flagcdn.com/w320/sk.png", "armenia": "https://flagcdn.com/w320/am.png", 
    "latvia": "https://flagcdn.com/w320/lv.png", "vietnam": "https://flagcdn.com/w320/vn.png", 
    "việt nam": "https://flagcdn.com/w320/vn.png", "thailand": "https://flagcdn.com/w320/th.png", 
    "thái lan": "https://flagcdn.com/w320/th.png", "indonesia": "https://flagcdn.com/w320/id.png", 
    "malaysia": "https://flagcdn.com/w320/my.png", "japan": "https://flagcdn.com/w320/jp.png", 
    "nhật bản": "https://flagcdn.com/w320/jp.png", "south korea": "https://flagcdn.com/w320/kr.png", 
    "hàn quốc": "https://flagcdn.com/w320/kr.png", "china": "https://flagcdn.com/w320/cn.png", 
    "trung quốc": "https://flagcdn.com/w320/cn.png", "india": "https://flagcdn.com/w320/in.png", 
    "panama": "https://flagcdn.com/w320/pa.png", "brazil": "https://flagcdn.com/w320/br.png", 
    "argentina": "https://flagcdn.com/w320/ar.png", "singapore": "https://flagcdn.com/w320/sg.png"
}

def clean_word(w: str) -> str:
    w_low = w.lower()
    if w_low in ['nu', 'nữ', 'women']: return 'Nữ'
    if w_low in ['nam', 'men']: return 'Nam'
    if w_low in ['u23', 'u21', 'u20', 'u19', 'u18', 'u17', 'u16']: return w.upper()
    return w.capitalize()

def get_logo_by_team(teams_str: str, raw_logo: str = "") -> str:
    if raw_logo and raw_logo.startswith("http") and not raw_logo.endswith("un.png"):
        return raw_logo
    t_lower = teams_str.lower()
    for key, url in LOGOS.items():
        if key in t_lower:
            return url
    return "https://flagcdn.com/w320/un.png"

def extract_teams_from_slug(url: str) -> str:
    try:
        match = re.search(r'/(?:truc-tiep|match|live|room|xem|phong|link|stream)/([^/?#]+)', url)
        if match:
            slug = match.group(1)
            if '-vs-' in slug:
                parts = slug.split('-vs-')
                t1_raw = re.sub(r'^(?:blv|caster|troc|chuoi|nho|kem|say)-[a-z0-9]+-', '', parts[0], flags=re.I)
                t2_raw = re.sub(r'-(?:luc|ngay|[a-z0-9]{8,}).*$', '', parts[1], flags=re.I)
                
                t1 = " ".join([clean_word(w) for w in t1_raw.split('-') if w])
                t2 = " ".join([clean_word(w) for w in t2_raw.split('-') if w])
                if t1 and t2:
                    return f"{t1} vs {t2}"
    except Exception:
        pass
    return ""

def extract_m3u8_stream(context, match_url):
    """Trích xuất chính xác đường dẫn .m3u8 hoặc .flv bằng cách nghe gói tin mạng"""
    page = context.new_page()
    captured_urls = []

    def handle_request(req):
        u = req.url
        if (".m3u8" in u or ".flv" in u) and "blob:" not in u and u not in captured_urls:
            captured_urls.append(u)

    page.on("request", handle_request)

    try:
        page.goto(match_url, timeout=12000, wait_until="domcontentloaded")
        time.sleep(1.5)

        # Tự động click vào trình phát để kích hoạt luồng video
        for selector in ["iframe", "video", ".play-btn", "button:has-text('HD1')", "button:has-text('HD2')", ".player-wrapper"]:
            try:
                el = page.query_selector(selector)
                if el:
                    el.click(timeout=800)
                    time.sleep(0.4)
            except Exception:
                pass

        for _ in range(6):
            if captured_urls:
                break
            time.sleep(0.3)

        if not captured_urls:
            for frame in page.frames:
                try:
                    content = frame.content()
                    urls = re.findall(r'https?://[^\s"\'<>]+\.(?:m3u8|flv)[^\s"\'<>]*', content)
                    for u in urls:
                        if "blob:" not in u and u not in captured_urls:
                            captured_urls.append(u)
                except Exception:
                    pass
    except Exception:
        pass
    finally:
        page.close()

    return captured_urls[0] if captured_urls else ""

def run_scraper():
    vn_tz = timezone(timedelta(hours=7))
    today_str = datetime.now(vn_tz).strftime("%d/%m")
    parsed_items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context(user_agent=USER_AGENT, timezone_id="Asia/Ho_Chi_Minh")
        page = context.new_page()

        try:
            print(f"[*] Đang nạp trang Chuối Chiên TV: {BASE_URL}")
            page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
            time.sleep(2)

            for _ in range(3):
                page.evaluate("window.scrollBy(0, 800)")
                time.sleep(0.4)

            # Bóc tách dữ liệu chi tiết từng thẻ trận đấu từ DOM
            raw_matches = page.evaluate('''() => {
                const results = [];
                const selector = 'a[href*="/truc-tiep/"], a[href*="/match/"], a[href*="/live/"], a[href*="/xem/"], a[href*="/room/"], a[href*="/phong/"]';
                const cards = document.querySelectorAll(selector);
                const seenUrls = new Set();

                cards.forEach(card => {
                    const href = card.getAttribute('href');
                    if (!href) return;
                    const fullUrl = href.startsWith('http') ? href : window.location.origin + href;
                    if (seenUrls.has(fullUrl)) return;
                    seenUrls.add(fullUrl);

                    let container = card;
                    let parent = card.parentElement;
                    while (parent && parent.tagName !== 'BODY') {
                        if (parent.querySelectorAll(selector).length > 1) break;
                        container = parent;
                        parent = parent.parentElement;
                    }

                    // Tìm tên từng đội từ các thẻ con
                    const homeEl = container.querySelector('.home-name, .team-home, .team1, .home, .name-home');
                    const awayEl = container.querySelector('.away-name, .team-away, .team2, .away, .name-away');
                    const blvEl = container.querySelector('.blv, .caster, .commentator, .author, .speaker');
                    const timeEl = container.querySelector('.time, .match-time, .start-time');
                    const imgEl = container.querySelector('img');

                    results.push({
                        url: fullUrl,
                        rawText: container.innerText || card.innerText || '',
                        homeName: homeEl ? homeEl.innerText.trim() : '',
                        awayName: awayEl ? awayEl.innerText.trim() : '',
                        blvName: blvEl ? blvEl.innerText.trim() : '',
                        timeStr: timeEl ? timeEl.innerText.trim() : '',
                        logo: imgEl ? (imgEl.src || imgEl.getAttribute('data-src') || '') : ''
                    });
                });
                return results;
            }''')

            page.close()
            print(f"[*] Thu thập được {len(raw_matches)} trận đấu. Đang trích xuất link phát video...")

            for item in raw_matches:
                match_url = item['url']
                card_text = item['rawText']

                # 1. BÓC TÁCH TÊN 2 ĐỘI BÓNG
                teams_title = ""
                if item['homeName'] and item['awayName']:
                    teams_title = f"{item['homeName']} vs {item['awayName']}"
                else:
                    vs_match = re.search(r'([A-Za-zÀ-ỹ0-9\s]+)\s+vs\s+([A-Za-zÀ-ỹ0-9\s]+)', card_text, re.I)
                    if vs_match:
                        t1 = vs_match.group(1).strip().title()
                        t2 = vs_match.group(2).strip().title()
                        teams_title = f"{t1} vs {t2}"
                    else:
                        teams_title = extract_teams_from_slug(match_url)

                if not teams_title:
                    teams_title = "Trận đấu Trực Tiếp"

                # 2. BÓC TÁCH TÊN BLV CHÍNH XÁC (Tránh trùng lặp)
                blv_name = ""
                if item['blvName']:
                    blv_name = item['blvName']
                else:
                    blv_match = re.search(r'((?:Chuối|Trốc|BLV|Caster|Gà|Lý)\s+[A-Za-zÀ-ỹ0-9\s\+]+)', card_text, re.I)
                    if blv_match:
                        blv_name = blv_match.group(1).strip()
                        blv_name = re.split(r'(?:hls|flv|live|trực tiếp|\d{1,2}:\d{2}|hiệp|cúp|league|\[)', blv_name, flags=re.I)[0].strip()

                if not blv_name:
                    slug_blv = re.search(r'/(?:blv|caster|chuoi|troc)-([a-z0-9-]+?)-', match_url, re.I)
                    if slug_blv:
                        blv_name = slug_blv.group(1).replace('-', ' ').title()

                clean_blv = re.sub(r'^(BLV|Caster)\s*[:\-]?\s*', '', blv_name, flags=re.I).strip()
                if not clean_blv:
                    clean_blv = "Chuối Chiên"

                # 3. BÓC TÁCH THỜI GIAN
                time_match = re.search(r'\b(2[0-3]|[0-1]?\d)[:h](\d{2})\b', card_text if not item['timeStr'] else item['timeStr'], re.I)
                if not time_match:
                    time_match = re.search(r'(?:luc|time)?[-_]?(2[0-3]|[0-1]\d)(\d{2})', match_url, re.I)
                extracted_time = f"{time_match.group(1).zfill(2)}:{time_match.group(2)}" if time_match else "19:00"

                date_match = re.search(r'ngay-(\d{1,2})[-_](\d{1,2})', match_url, re.I)
                match_date = f"{date_match.group(1).zfill(2)}/{date_match.group(2).zfill(2)}" if date_match else today_str

                # 4. TRÍCH XUẤT M3U8 STREAM & LOGO
                m3u8_url = extract_m3u8_stream(context, match_url)
                final_logo = get_logo_by_team(teams_title, item['logo'])
                
                stream_type = "[flv]" if "flv" in match_url.lower() or "flv" in m3u8_url.lower() else "[hls]"

                # Tiêu đề đúng mẫu giao diện: 20:00 25/09 ⚽ Indonesia vs Singapore (Trốc Tru) [FHD] [hls]
                full_title = f"{extracted_time} {match_date} ⚽ {teams_title} ({clean_blv}) [FHD] {stream_type}"

                try:
                    d, m = map(int, match_date.split('/'))
                    h, mins = map(int, extracted_time.split(':'))
                    dt_obj = datetime(datetime.now(vn_tz).year, m, d, h, mins, tzinfo=vn_tz)
                except:
                    dt_obj = datetime(2099, 1, 1, 0, 0, tzinfo=vn_tz)

                # Dùng trực tiếp luồng video .m3u8 bắt được
                playable_stream = m3u8_url if m3u8_url else match_url

                parsed_items.append({
                    "title": full_title,
                    "logo": final_logo,
                    "stream_url": playable_stream,
                    "is_live": bool(m3u8_url),
                    "dt": dt_obj,
                    "match_url": match_url
                })

            # Sắp xếp theo thứ tự thời gian
            parsed_items.sort(key=lambda x: (x['dt'].date(), not x['is_live'], x['dt'].time()))

            seen_urls = set()
            for p_item in parsed_items:
                if p_item['match_url'] in seen_urls:
                    continue
                seen_urls.add(p_item['match_url'])
                final_matches.append(p_item)

        except Exception as e:
            print(f"[!] Lỗi: {e}")
        finally:
            browser.close()

    # Xuất file M3U Playlist
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write('#EXTM3U\n\n')
        for item in final_matches:
            logo_attr = f'tvg-logo="{item["logo"]}"' if item["logo"] else ''
            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}" , {item["title"]} \n')
            f.write(f'#EXTVLCOPT:http-referrer={BASE_URL}/\n')
            f.write(f'{item["stream_url"]}\n\n')

    print(f"[*] Đã xuất thành công {len(final_matches)} trận vào file {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
