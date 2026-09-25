import time
import re
import sys
from datetime import datetime, timezone, timedelta
from urllib.parse import quote, urljoin
from playwright.sync_api import sync_playwright

BASE_URL = "https://live07.chuoichientv.me"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Chuối Chiên TV"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

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
    "slovakia": "https://flagcdn.com/w320/sk.png", "armenia": "https://flagcdn.com/w320/am.png", 
    "latvia": "https://flagcdn.com/w320/lv.png", "turkiye": "https://flagcdn.com/w320/tr.png", "thổ nhĩ kỳ": "https://flagcdn.com/w320/tr.png",
    "belgium": "https://flagcdn.com/w320/be.png", "bỉ": "https://flagcdn.com/w320/be.png",
    "poland": "https://flagcdn.com/w320/pl.png", "ba lan": "https://flagcdn.com/w320/pl.png",
    "hungary": "https://flagcdn.com/w320/hu.png", "ukraine": "https://flagcdn.com/w320/ua.png",

    # Châu Á & Đông Nam Á
    "vietnam": "https://flagcdn.com/w320/vn.png", "việt nam": "https://flagcdn.com/w320/vn.png",
    "thailand": "https://flagcdn.com/w320/th.png", "thái lan": "https://flagcdn.com/w320/th.png",
    "indonesia": "https://flagcdn.com/w320/id.png", "malaysia": "https://flagcdn.com/w320/my.png",
    "japan": "https://flagcdn.com/w320/jp.png", "nhật bản": "https://flagcdn.com/w320/jp.png",
    "south korea": "https://flagcdn.com/w320/kr.png", "hàn quốc": "https://flagcdn.com/w320/kr.png",
    "china": "https://flagcdn.com/w320/cn.png", "trung quốc": "https://flagcdn.com/w320/cn.png",
    "india": "https://flagcdn.com/w320/in.png", "panama": "https://flagcdn.com/w320/pa.png",
    "singapore": "https://flagcdn.com/w320/sg.png", "bangladesh": "https://flagcdn.com/w320/bd.png",
    "australia": "https://flagcdn.com/w320/au.png", "úc": "https://flagcdn.com/w320/au.png",

    # Nam Mỹ
    "brazil": "https://flagcdn.com/w320/br.png", "argentina": "https://flagcdn.com/w320/ar.png",
    "uruguay": "https://flagcdn.com/w320/uy.png", "ecuador": "https://flagcdn.com/w320/ec.png"
}

def clean_word(w: str) -> str:
    w_low = w.lower()
    if w_low in ['nu', 'nữ', 'women']: return 'Nữ'
    if w_low in ['nam', 'men']: return 'Nam'
    if w_low in ['u23', 'u21', 'u20', 'u19', 'u18', 'u17', 'u16']: return w.upper()
    return w.capitalize()

def get_team_logo(teams_str: str) -> str:
    t_lower = teams_str.lower()
    for key, url in LOGOS.items():
        if key in t_lower:
            return url
    return "https://flagcdn.com/w320/un.png"

def parse_teams_and_blv_from_slug(url: str, card_text: str):
    teams_title = ""
    blv_name = ""

    # 1. Tìm tên 2 đội từ Text của Thẻ
    vs_match = re.search(r'([A-Za-zÀ-ỹ0-9\s]{2,25})\s+vs\s+([A-Za-zÀ-ỹ0-9\s]{2,25})', card_text, re.I)
    if vs_match:
        t1 = vs_match.group(1).strip().title()
        t2 = vs_match.group(2).strip().title()
        t1 = re.sub(r'^(Trực Tiếp|Xem|Bóng Đá|Trận|Fhd|Hls|Flv)\s*', '', t1, flags=re.I).strip()
        if t1 and t2 and len(t1) > 1 and len(t2) > 1:
            teams_title = f"{t1} vs {t2}"

    # 2. Nếu text không có, bóc tách chính xác tên 2 đội từ URL Slug
    try:
        match = re.search(r'/(?:truc-tiep|match|live|room|xem|phong|link|stream)/([^/?#]+)', url)
        slug = match.group(1) if match else url.split('/')[-1]
        
        if '-vs-' in slug:
            parts = slug.split('-vs-')
            t1_slug = parts[0]
            t2_slug = parts[1]

            # Nhận diện BLV trong URL Slug nếu có
            blv_in_slug = re.search(r'^(?:blv|caster|troc|chuoi|nho|kem|say|ga|ly|chao|la|ngao)-([a-z0-9-]+?)-(?=[a-z0-9]+-)', t1_slug, re.I)
            if blv_in_slug:
                blv_name = blv_in_slug.group(1).replace('-', ' ').title()

            # Làm sạch Slug đội 1
            t1_slug = re.sub(r'^(?:blv|caster|troc|chuoi|nho|kem|say|ga|ly|chao|la|ngao)-[a-z0-9]+-', '', t1_slug, flags=re.I)
            t1_slug = re.sub(r'^(?:blv|caster|troc-tru|chuoi-nho|chuoi-chao|chuoi-la|chuoi-ngao|chuoi-kem|chuoi-say)-', '', t1_slug, flags=re.I)
            t1_slug = re.sub(r'^(?:truc-tiep|xem-truc-tiep|match|live)-', '', t1_slug, flags=re.I)

            # Làm sạch Slug đội 2
            t2_slug = re.sub(r'-(?:luc|ngay|[a-z0-9]{8,}).*$', '', t2_slug, flags=re.I)
            t2_slug = re.sub(r'-\d{3,4}$', '', t2_slug, flags=re.I)

            t1 = " ".join([clean_word(w) for w in t1_slug.split('-') if w])
            t2 = " ".join([clean_word(w) for w in t2_slug.split('-') if w])

            if not teams_title and t1 and t2:
                teams_title = f"{t1} vs {t2}"
    except Exception:
        pass

    # 3. Bóc tách tên BLV đặc trưng của Chuối Chiên TV
    if not blv_name:
        known_blvs = ["Trốc Tru", "Chuối Nhỏ", "Chuối Chao", "Chuối Lá", "Chuối Ngao", "Chuối Kem", "Chuối Sấy", "Chuối Lập", "Chuối Kỷ", "Trốc"]
        for b in known_blvs:
            if b.lower() in card_text.lower() or b.lower().replace(' ', '-') in url.lower():
                blv_name = b
                break

    if not blv_name:
        match = re.search(r'\(([^)]+)\)', card_text)
        if match:
            val = match.group(1).strip()
            if not any(k in val.lower() for k in ["fhd", "hls", "flv", "hd", "geo"]):
                blv_name = val

    if not blv_name:
        blv_name = "Chuối Chiên"

    if not teams_title:
        teams_title = "Trận đấu Trực Tiếp"

    return teams_title, blv_name

def run_scraper():
    vn_tz = timezone(timedelta(hours=7))
    today_str = datetime.now(vn_tz).strftime("%d/%m")
    parsed_items = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-setuid-sandbox"]
            )
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 720},
                timezone_id="Asia/Ho_Chi_Minh",
                locale="vi-VN"
            )
            page = context.new_page()

            print(f"[*] Kết nối tới: {BASE_URL}")
            page.goto(BASE_URL, timeout=45000, wait_until="domcontentloaded")
            time.sleep(2.5)

            for _ in range(3):
                page.evaluate("window.scrollBy(0, 800)")
                time.sleep(0.4)

            # Quét toàn bộ thẻ trận đấu trực tiếp từ Trang chủ
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

                    results.push({
                        url: fullUrl,
                        rawText: container.innerText || card.innerText || ''
                    });
                });
                return results;
            }''')

            page.close()
            browser.close()

            print(f"[*] Quét thành công {len(raw_matches)} trận. Đang tiến hành bóc tách dữ liệu...")

            for item in raw_matches:
                try:
                    match_url = item['url']
                    card_text = item['rawText']

                    teams_title, blv_name = parse_teams_and_blv_from_slug(match_url, card_text)

                    # Bóc tách Giờ & Ngày
                    time_match = re.search(r'\b(2[0-3]|[0-1]?\d)[:h](\d{2})\b', card_text, re.I)
                    if not time_match:
                        time_match = re.search(r'(?:luc|time)?[-_]?(2[0-3]|[0-1]\d)(\d{2})', match_url, re.I)
                    extracted_time = f"{time_match.group(1).zfill(2)}:{time_match.group(2)}" if time_match else "19:00"

                    date_match = re.search(r'ngay-(\d{1,2})[-_](\d{1,2})', match_url, re.I)
                    match_date = f"{date_match.group(1).zfill(2)}/{date_match.group(2).zfill(2)}" if date_match else today_str

                    final_logo = get_team_logo(teams_title)
                    stream_type = "[flv]" if "flv" in match_url.lower() else "[hls]"

                    # Cấu trúc tiêu đề chuẩn theo đúng giao diện mẫu Thể Thao Full
                    full_title = f"{extracted_time} {match_date} ⚽ {teams_title} ({blv_name}) [FHD] {stream_type}"

                    try:
                        d, m = map(int, match_date.split('/'))
                        h, mins = map(int, extracted_time.split(':'))
                        dt_obj = datetime(datetime.now(vn_tz).year, m, d, h, mins, tzinfo=vn_tz)
                    except Exception:
                        dt_obj = datetime(2099, 1, 1, 0, 0, tzinfo=vn_tz)

                    parsed_items.append({
                        "title": full_title,
                        "logo": final_logo,
                        "stream_url": match_url,
                        "dt": dt_obj,
                        "match_url": match_url
                    })
                except Exception as item_err:
                    continue

            # Sắp xếp theo ngày thi đấu -> thời gian
            parsed_items.sort(key=lambda x: (x['dt'].date(), x['dt'].time()))

    except Exception as e:
        print(f"[!] Lỗi tiến trình Playwright: {e}")

    # GHI FILE M3U PLAYLIST ĐẢM BẢO KHÔNG BAO GIỜ BỊ TRỐNG
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write('#EXTM3U tvg-shift="0"\n\n')
        seen_urls = set()
        for item in parsed_items:
            if item['match_url'] in seen_urls:
                continue
            seen_urls.add(item['match_url'])

            logo_attr = f'tvg-logo="{item["logo"]}"' if item["logo"] else ''
            
            # Đính kèm tham số User-Agent & Referer tiêu chuẩn để app IPTV tự kết nối phát trực tiếp
            playable_url = f"{item['stream_url']}|User-Agent={USER_AGENT}&Referer={BASE_URL}/"

            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}" , {item["title"]} \n')
            f.write(f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n')
            f.write(f'#EXTVLCOPT:http-referrer={BASE_URL}/\n')
            f.write(f'{playable_url}\n\n')

    print(f"[*] Xuất hoàn tất {len(parsed_items)} trận vào file {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
