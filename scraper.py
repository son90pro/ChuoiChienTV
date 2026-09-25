import time
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
from playwright.sync_api import sync_playwright

WORKER_DOMAIN = "chuoi-chien-iptv.sonnguyen90pro.workers.dev"
BASE_URL = "https://live07.chuoichientv.me"
OUTPUT_FILE = "playlist.m3u"

# Tên nhóm danh mục hiển thị trên ứng dụng IPTV giống hình mẫu
GROUP_NAME = "Chuối Chiên TV"

# Bảng tra cứu cờ quốc gia chuẩn hóa
LOGOS = {
    # Châu Âu
    "netherlands": "https://flagcdn.com/w320/nl.png", "hà lan": "https://flagcdn.com/w320/nl.png",
    "germany": "https://flagcdn.com/w320/de.png", "đức": "https://flagcdn.com/w320/de.png",
    "spain": "https://flagcdn.com/w320/es.png", "tây ban nha": "https://flagcdn.com/w320/es.png",
    "france": "https://flagcdn.com/w320/fr.png", "pháp": "https://flagcdn.com/w320/fr.png",
    "italy": "https://flagcdn.com/w320/it.png", "ý": "https://flagcdn.com/w320/it.png",
    "portugal": "https://flagcdn.com/w320/pt.png", "bồ đào nha": "https://flagcdn.com/w320/pt.png",
    "england": "https://flagcdn.com/w320/gb-eng.png", "anh": "https://flagcdn.com/w320/gb-eng.png",
    "wales": "https://flagcdn.com/w320/gb-wls.png", "scotland": "https://flagcdn.com/w320/gb-sct.png",
    "andorra": "https://flagcdn.com/w320/ad.png", "malta": "https://flagcdn.com/w320/mt.png",
    "Slovakia": "https://flagcdn.com/w320/sk.png", "Armenia": "https://flagcdn.com/w320/am.png", "Latvia": "https://flagcdn.com/w320/lv.png",

    # Châu Á & Trung Đông
    "vietnam": "https://flagcdn.com/w320/vn.png", "việt nam": "https://flagcdn.com/w320/vn.png",
    "thailand": "https://flagcdn.com/w320/th.png", "thái lan": "https://flagcdn.com/w320/th.png",
    "indonesia": "https://flagcdn.com/w320/id.png", "malaysia": "https://flagcdn.com/w320/my.png",
    "japan": "https://flagcdn.com/w320/jp.png", "nhật bản": "https://flagcdn.com/w320/jp.png",
    "south korea": "https://flagcdn.com/w320/kr.png", "hàn quốc": "https://flagcdn.com/w320/kr.png", "korea": "https://flagcdn.com/w320/kr.png",
    "china": "https://flagcdn.com/w320/cn.png", "trung quốc": "https://flagcdn.com/w320/cn.png",
    "qatar": "https://flagcdn.com/w320/qa.png", "bahrain": "https://flagcdn.com/w320/bh.png",
    "india": "https://flagcdn.com/w320/in.png", "panama": "https://flagcdn.com/w320/pa.png",

    # Châu Phi & Nam Mỹ
    "brazil": "https://flagcdn.com/w320/br.png", "argentina": "https://flagcdn.com/w320/ar.png",
    "uruguay": "https://flagcdn.com/w320/uy.png", "ecuador": "https://flagcdn.com/w320/ec.png"
}

def get_team_logo_url(teams_str: str) -> str:
    t_lower = teams_str.lower()
    for key, url in LOGOS.items():
        if key in t_lower:
            return url
    return "https://flagcdn.com/w320/un.png"

def clean_word(w: str) -> str:
    w_low = w.lower()
    if w_low in ['nu', 'nữ', 'women']: return 'Women' if w_low == 'women' else 'Nữ'
    if w_low in ['nam', 'men']: return 'Men' if w_low == 'men' else 'Nam'
    if w_low in ['u23', 'u21', 'u20', 'u19', 'u18', 'u17', 'u16', 'u15']: return w.upper()
    if w_low in ['ir', 'uae', 'usa', 'uk']: return w.upper()
    return w.capitalize()

def parse_teams_from_url(url: str) -> str:
    try:
        match = re.search(r'/(?:truc-tiep|match|live|room|xem|phong|link|stream|xem-bong-da|truc-tiep-bong-da)/([^/?#]+)', url)
        if match:
            slug = match.group(1)
        else:
            parts_url = url.split('/')
            slug = next((p for p in parts_url if '-vs-' in p), "")
            
        if not slug or '-vs-' not in slug:
            return ""

        parts = slug.split('-vs-')
        if len(parts) != 2:
            return ""

        team1_slug, team2_slug = parts[0], parts[1]

        team1_slug = re.sub(r'^(?:blv-)?(?:ga|caster|chuoi|troc|nho|kem|lap|ky)-(?:sieu-[a-z0-9]+|[a-z0-9]+)-', '', team1_slug, flags=re.IGNORECASE)
        team1_slug = re.sub(r'^blv-[a-z0-9]+-', '', team1_slug, flags=re.IGNORECASE)
        
        team2_slug = re.sub(r'-luc-\d+.*$', '', team2_slug, flags=re.IGNORECASE)
        team2_slug = re.sub(r'-ngay-\d+.*$', '', team2_slug, flags=re.IGNORECASE)
        team2_slug = re.sub(r'-\d{3,4}$', '', team2_slug, flags=re.IGNORECASE)
        team2_slug = re.sub(r'-[a-z0-9]{8,35}$', '', team2_slug, flags=re.IGNORECASE)

        t1 = " ".join([clean_word(w) for w in team1_slug.split('-') if w])
        t2 = " ".join([clean_word(w) for w in team2_slug.split('-') if w])

        if t1 and t2:
            return f"{t1} vs {t2}"
    except Exception:
        pass
    return ""

def parse_date_info(url: str, text: str, default_date: str) -> str:
    try:
        date_match = re.search(r'ngay-(\d{1,2})[-_](\d{1,2})', url, re.IGNORECASE)
        if date_match:
            d, m = date_match.group(1).zfill(2), date_match.group(2).zfill(2)
            return f"{d}/{m}"
            
        text_date_match = re.search(r'\b(\d{1,2})[/.-](\d{1,2})\b', text)
        if text_date_match:
            d, m = text_date_match.group(1).zfill(2), text_date_match.group(2).zfill(2)
            return f"{d}/{m}"
    except Exception:
        pass
    return default_date

def parse_time_robust(url: str, text: str) -> str:
    text_time = re.search(r'\b(2[0-3]|[0-1]?\d)[:h](\d{2})\b', text, re.IGNORECASE)
    if text_time:
        return f"{text_time.group(1).zfill(2)}:{text_time.group(2)}"

    url_luc_4 = re.search(r'(?:luc|time)?[-_]?(2[0-3]|[0-1]\d)(\d{2})', url, re.IGNORECASE)
    if url_luc_4:
        return f"{url_luc_4.group(1).zfill(2)}:{url_luc_4.group(2)}"

    return "00:00"

def parse_datetime_obj(date_str: str, time_str: str, vn_tz) -> datetime:
    now = datetime.now(vn_tz)
    try:
        d, m = map(int, date_str.split('/'))
        h, mins = map(int, time_str.split(':'))
        yr = now.year
        if now.month == 12 and m == 1:
            yr += 1
        elif now.month == 1 and m == 12:
            yr -= 1
        return datetime(yr, m, d, h, mins, tzinfo=vn_tz)
    except Exception:
        return datetime(2099, 1, 1, 0, 0, tzinfo=vn_tz)

def get_match_details(context, match_url):
    page = context.new_page()
    page.route("**/*.{png,jpg,jpeg,svg,css,woff,woff2}", lambda route: route.abort())
    
    m3u8_found = []
    def handle_request(request):
        url = request.url
        if (".m3u8" in url or ".flv" in url) and "blob:" not in url and url not in m3u8_found:
            m3u8_found.append(url)
            
    page.on("request", handle_request)
    match_info = {"time_str": "", "m3u8_url": "", "is_live": False}

    try:
        page.goto(match_url, timeout=12000, wait_until="domcontentloaded")
        
        try:
            page.click('.play-btn, .btn-play, #player, iframe, video, .player-wrapper', timeout=1500)
        except Exception:
            pass

        for _ in range(8):
            if m3u8_found:
                break
            time.sleep(0.4)

        if not m3u8_found:
            for frame in page.frames:
                try:
                    content = frame.content()
                    urls = re.findall(r'https?://[^\s"\'<>]+\.(?:m3u8|flv)[^\s"\'<>]*', content)
                    for u in urls:
                        if "blob:" not in u and u not in m3u8_found:
                            m3u8_found.append(u)
                except Exception:
                    pass

        match_info["m3u8_url"] = m3u8_found[0] if m3u8_found else ""

        details = page.evaluate('''() => {
            let tStr = "";
            let liveState = false;
            const fullBody = document.body.innerText || '';
            if (/(hiệp 1|hiệp 2|hiệp phụ|h1|h2|đang đá|đang diễn ra|\\d+['’]|live)/i.test(fullBody)) {
                liveState = true;
            }

            const timeEls = Array.from(document.querySelectorAll('span, div, p, time, b'));
            for (let el of timeEls) {
                const text = el.innerText ? el.innerText.trim() : '';
                if (/\\d{1,2}[:h]\\d{2}/.test(text) && text.length < 30) {
                    tStr = text;
                    break;
                }
            }
            return { timeStr: tStr, liveState: liveState };
        }''')

        if details['timeStr']:
            match_info["time_str"] = details['timeStr']
        match_info["is_live"] = details['liveState'] or bool(match_info["m3u8_url"])

    except Exception:
        pass
    finally:
        page.close()

    return match_info

def run_scraper():
    vn_tz = timezone(timedelta(hours=7))
    today_str = datetime.now(vn_tz).strftime("%d/%m")
    
    final_matches = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            timezone_id="Asia/Ho_Chi_Minh",
            locale="vi-VN"
        )
        page = context.new_page()

        raw_matches = []
        try:
            print(f"[*] Đang tải trang Chuối Chiên TV: {BASE_URL}")
            page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
            
            try:
                page.evaluate('''() => {
                    const tabs = Array.from(document.querySelectorAll('button, div, span, a')).filter(el => {
                        const t = (el.innerText || '').trim().toLowerCase();
                        return t === 'tất cả' || t === 'đang diễn ra' || t === 'trực tiếp' || t === 'live';
                    });
                    tabs.forEach(t => { try { t.click(); } catch(e){} });
                }''')
                time.sleep(1)
            except Exception:
                pass

            for _ in range(4):
                page.evaluate("window.scrollBy(0, 800)")
                time.sleep(0.5)

            raw_matches = page.evaluate('''() => {
                const matches = [];
                const links = Array.from(document.querySelectorAll('a[href*="/truc-tiep/"], a[href*="/match/"], a[href*="/live/"], a[href*="/xem/"], a[href*="/room/"], a[href*="/phong/"], a[href*="/truc-tiep-bong-da/"], a[href*="/xem-bong-da/"]'));
                const seenUrls = new Set();

                links.forEach(link => {
                    const href = link.getAttribute('href');
                    if (!href) return;

                    const fullUrl = href.startsWith('http') ? href : window.location.origin + href;
                    if (seenUrls.has(fullUrl)) return;
                    seenUrls.add(fullUrl);

                    let card = link;
                    let parent = link.parentElement;
                    while (parent && parent.tagName !== 'BODY') {
                        if (parent.querySelectorAll('a').length === 1) {
                            card = parent;
                            parent = parent.parentElement;
                        } else {
                            break;
                        }
                    }

                    const fullText = card ? card.innerText || '' : link.innerText || '';

                    matches.push({
                        url: fullUrl,
                        fullText: fullText
                    });
                });

                return matches;
            }''')

            page.close()
            print(f"[*] Quét được {len(raw_matches)} trận đấu. Đang phân tích chi tiết...")

            parsed_items = []
            for item in raw_matches:
                text = item['fullText']
                url = item['url']
                if not text:
                    continue

                details = get_match_details(context, url)

                raw_time_text = details['time_str'] if details['time_str'] else text
                extracted_time = parse_time_robust(url, raw_time_text)
                match_date = parse_date_info(url, text, today_str)

                is_currently_live = details['is_live'] or any(k in text.lower() for k in ["hiệp 1", "hiệp 2", "đang đá", "đang diễn ra", "live"])

                # Bóc tách tên BLV theo chuẩn mẫu (Trốc Tru, Chuối Nhỏ, Chuối Kem, Chuối Sấy...)
                blv_name = ""
                blv_match = re.search(r'((?:Chuối|Trốc|BLV|Caster|Đội|Nhà)\s+[A-Za-zÀ-ỹ0-9\s\+]+)', text, re.IGNORECASE)
                if blv_match:
                    raw_blv = blv_match.group(1).strip()
                    raw_blv = re.split(r'(?:hls|flv|live|trực tiếp|\d{1,2}:\d{2}|hiệp|cúp|league|\[)', raw_blv, flags=re.IGNORECASE)[0].strip()
                    blv_name = raw_blv

                # Thử quét từ slug URL nếu không tìm thấy trong text
                if not blv_name:
                    slug_blv_match = re.search(r'/(?:blv|caster|chuoi|troc)-([a-z0-9-]+?)-', url, re.I)
                    if slug_blv_match:
                        blv_name = slug_blv_match.group(1).replace('-', ' ').title()

                clean_blv = re.sub(r'^(BLV|Caster)\s*[:\-]?\s*', '', blv_name, flags=re.IGNORECASE).strip()
                if not clean_blv:
                    clean_blv = "Chuối Chiên"

                teams_str = parse_teams_from_url(url)
                if not teams_str:
                    teams_str = "Trận đấu Trực Tiếp"

                logo = get_team_logo_url(teams_str)
                stream_type = "[flv]" if "flv" in url.lower() or "stream2" in url.lower() else "[hls]"

                # ĐỊNH DẠNG CHUẨN GIỐNG HÌNH MẪU 1806: 20:00 25/09 ⚽ Indonesia vs Singapore (Trốc Tru) [FHD] [hls]
                full_title = f"{extracted_time} {match_date} ⚽ {teams_str} ({clean_blv}) [FHD] {stream_type}".strip()

                dt_obj = parse_datetime_obj(match_date, extracted_time, vn_tz)

                parsed_items.append({
                    "title": full_title,
                    "logo": logo,
                    "url": url,
                    "m3u8_url": details['m3u8_url'],
                    "is_live": is_currently_live,
                    "date": match_date,
                    "time": extracted_time,
                    "dt": dt_obj
                })

            # Sắp xếp theo ngày hôm nay lên đầu, trận LIVE ưu tiên, tiếp đến giờ tăng dần
            parsed_items.sort(key=lambda x: (x['dt'].date(), not x['is_live'], x['dt'].time()))

            seen_urls = set()
            title_tracker = {}

            for p_item in parsed_items:
                if p_item['url'] in seen_urls:
                    continue
                seen_urls.add(p_item['url'])

                raw_title = p_item['title']
                if raw_title in title_tracker:
                    title_tracker[raw_title] += 1
                    p_item['title'] = f"{raw_title} (SV{title_tracker[raw_title]})"
                else:
                    title_tracker[raw_title] = 1

                final_matches.append(p_item)

        except Exception as e:
            print(f"[!] Lỗi: {e}")
        finally:
            browser.close()

    # Ghi file M3U Playlist đúng chuẩn định dạng phát mượt
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write('#EXTM3U tvg-shift="0"\n\n')

        for item in final_matches:
            logo_attr = f'tvg-logo="{item["logo"]}"' if item["logo"] else 'tvg-logo="https://flagcdn.com/w320/un.png"'
            
            if item.get('m3u8_url'):
                stream_url = f"https://{WORKER_DOMAIN}/proxy?url={quote(item['m3u8_url'], safe='')}"
            else:
                stream_url = f"https://{WORKER_DOMAIN}/live?url={quote(item['url'], safe='')}"
            
            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}",{item["title"]}\n')
            f.write(f'#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\n')
            f.write(f'#EXTVLCOPT:http-referrer={BASE_URL}/\n')
            f.write(f'{stream_url}|User-Agent=Mozilla/5.0&Referer={BASE_URL}/\n\n')

    print(f"[*] Đã xuất {len(final_matches)} trận vào file {OUTPUT_FILE} (Group: {GROUP_NAME}) thành công!")

if __name__ == "__main__":
    run_scraper()
    
