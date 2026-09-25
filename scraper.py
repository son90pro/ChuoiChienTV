import time
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, quote
from playwright.sync_api import sync_playwright

BASE_URL = "https://phalang.live"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Phá Làng TV"
REFERRER_HEADER = "https://phalang.live/"
WORKER_DOMAIN = "pha-lang-iptv.sonnguyen90pro.workers.dev"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Bảng tra cứu cờ quốc gia chuẩn hóa
FLAG_LOGOS = {
    "china": "https://flagcdn.com/w320/cn.png", "trung quốc": "https://flagcdn.com/w320/cn.png",
    "vietnam": "https://flagcdn.com/w320/vn.png", "việt nam": "https://flagcdn.com/w320/vn.png",
    "bangladesh": "https://flagcdn.com/w320/bd.png", "malaysia": "https://flagcdn.com/w320/my.png",
    "australia": "https://flagcdn.com/w320/au.png", "úc": "https://flagcdn.com/w320/au.png",
    "brazil": "https://flagcdn.com/w320/br.png", "japan": "https://flagcdn.com/w320/jp.png",
    "nhật bản": "https://flagcdn.com/w320/jp.png", "philippines": "https://flagcdn.com/w320/ph.png",
    "south korea": "https://flagcdn.com/w320/kr.png", "hàn quốc": "https://flagcdn.com/w320/kr.png",
    "indonesia": "https://flagcdn.com/w320/id.png", "singapore": "https://flagcdn.com/w320/sg.png",
    "uzbekistan": "https://flagcdn.com/w320/uz.png", "saudi arabia": "https://flagcdn.com/w320/sa.png",
    "thailand": "https://flagcdn.com/w320/th.png", "thái lan": "https://flagcdn.com/w320/th.png",
    "england": "https://flagcdn.com/w320/gb-eng.png", "anh": "https://flagcdn.com/w320/gb-eng.png",
    "spain": "https://flagcdn.com/w320/es.png", "tây ban nha": "https://flagcdn.com/w320/es.png",
    "germany": "https://flagcdn.com/w320/de.png", "đức": "https://flagcdn.com/w320/de.png",
    "france": "https://flagcdn.com/w320/fr.png", "pháp": "https://flagcdn.com/w320/fr.png",
    "italy": "https://flagcdn.com/w320/it.png", "ý": "https://flagcdn.com/w320/it.png"
}

def clean_team_name(name: str) -> str:
    if not name:
        return ""
    s = re.sub(r'^(?:blv|caster|ga|ly)-[a-z0-9]+-', '', name, flags=re.I)
    s = re.sub(r'-(?:luc|ngay|[a-z0-9]{8,}).*$', '', s, flags=re.I)
    return s.replace('-', ' ').strip().title()

def process_logo_url(raw_logo: str, team1_name: str, teams_title: str) -> str:
    t1_lower = team1_name.lower().strip()
    for k, v in FLAG_LOGOS.items():
        if k in t1_lower:
            return v
    t_lower = teams_title.lower()
    for k, v in FLAG_LOGOS.items():
        if k in t_lower:
            return v
    if raw_logo and not raw_logo.startswith("data:image"):
        if raw_logo.startswith("//"):
            return "https:" + raw_logo
        elif raw_logo.startswith("http"):
            return raw_logo
        elif raw_logo.startswith("/"):
            return urljoin(BASE_URL, raw_logo)
    return "https://flagcdn.com/w320/un.png"

def parse_time_robust(url: str, text: str) -> str:
    text_time = re.search(r'\b(2[0-3]|[0-1]?\d)[:h](\d{2})\b', text, re.I)
    if text_time:
        hh = text_time.group(1).zfill(2)
        mm = text_time.group(2)
        return f"{hh}:{mm}"

    url_luc_4 = re.search(r'(?:luc|time)?[-_]?(2[0-3]|[0-1]\d)(\d{2})', url, re.I)
    if url_luc_4:
        hh = url_luc_4.group(1).zfill(2)
        mm = url_luc_4.group(2)
        return f"{hh}:{mm}"

    return "00:00"

def parse_date_info(url: str, text: str, default_date: str) -> str:
    try:
        date_match = re.search(r'ngay-(\d{1,2})[-_](\d{1,2})', url, re.I)
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

def parse_blv_name(card_text: str, match_url: str) -> str:
    slug_blv = re.search(r'/(?:truc-tiep|match|live)/.*?blv-([a-z0-9-]+?)-(?:vs|[a-z0-9]+-vs)', match_url, re.I)
    if slug_blv:
        return slug_blv.group(1).replace('-', ' ').upper()
    match = re.search(r'\b((?:BLV|Caster|Bình Luận Viên|Gà|Lý)\s+[A-Za-zÀ-ỹ0-9\s]+)\b', card_text, re.I)
    if match:
        blv = match.group(1).strip()
        return re.sub(r'^(?:Bình Luận Viên|Caster|Gà)\s*', '', blv, flags=re.I).upper()
    return "PHÁ LÀNG"

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

def run_scraper():
    vn_tz = timezone(timedelta(hours=7))
    today_str = datetime.now(vn_tz).strftime("%d/%m")
    parsed_items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 3000},
            timezone_id="Asia/Ho_Chi_Minh",
            locale="vi-VN"
        )
        page = context.new_page()

        try:
            print(f"[*] Đang kết nối tới Phá Làng TV: {BASE_URL}")
            page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
            time.sleep(3)

            # Cuộn trang nạp đủ các thẻ trận
            for _ in range(4):
                page.evaluate("window.scrollBy(0, 800)")
                time.sleep(0.5)

            raw_cards = page.evaluate('''() => {
                const results = [];
                const selector = 'a[href*="/truc-tiep/"], a[href*="/xem-truc-tiep/"], a[href*="/match/"], a[href*="/live/"], a[href*="/phong/"]';
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

                    let logo = '';
                    const img = container.querySelector('img');
                    if (img) logo = img.src || img.getAttribute('data-src') || '';

                    results.push({
                        url: fullUrl,
                        logo: logo,
                        rawText: container.innerText || card.innerText || ''
                    });
                });
                return results;
            }''')

            print(f"[*] Quét thành công {len(raw_cards)} trận. Đang phân tích dữ liệu...")

            for item in raw_cards:
                match_url = item['url']
                raw_logo = item['logo']
                card_text = item['rawText']

                team1_name = ""
                teams_title = ""
                slug_match = re.search(r'/(?:truc-tiep|xem-truc-tiep|match|live|phong)/([^/?#]+)', match_url)
                if slug_match:
                    slug = slug_match.group(1)
                    if "-vs-" in slug:
                        parts = slug.split('-vs-')
                        t1 = clean_team_name(parts[0])
                        t2 = clean_team_name(parts[1])
                        if t1 and t2:
                            team1_name = t1
                            teams_title = f"{t1} vs {t2}"

                if not teams_title:
                    teams_title = "Trận đấu Trực Tiếp"

                final_logo = process_logo_url(raw_logo, team1_name, teams_title)

                # Nhận diện trạng thái trận LIVE
                is_currently_live = bool(re.search(r'(hiệp 1|hiệp 2|hiệp phụ|h1|h2|đang đá|đang diễn ra|\d+[\'’]|live|trực tiếp)', card_text, re.I))

                extracted_time = parse_time_robust(match_url, card_text)
                match_date = parse_date_info(match_url, card_text, today_str)
                blv_name = parse_blv_name(card_text, match_url)

                blv_suffix = f" ({blv_name.title()})" if blv_name else ""
                
                if is_currently_live:
                    title_fmt = f"[{match_date} - 🔴 LIVE {extracted_time}] {teams_title}{blv_suffix}"
                else:
                    title_fmt = f"[{match_date} - {extracted_time}] {teams_title}{blv_suffix}"

                # Đi qua Cloudflare Worker proxy để giải mã link phát trực tiếp khi mở app
                stream_url = f"https://{WORKER_DOMAIN}/live?url={quote(match_url, safe='')}"
                dt_obj = parse_datetime_obj(match_date, extracted_time, vn_tz)

                parsed_items.append({
                    "title": title_fmt,
                    "logo": final_logo,
                    "stream_url": stream_url,
                    "is_live": is_currently_live,
                    "date": match_date,
                    "time": extracted_time,
                    "dt": dt_obj,
                    "match_url": match_url
                })

            # Sắp xếp: Ngày hôm nay -> Trận LIVE -> Thứ tự giờ đá
            parsed_items.sort(key=lambda x: (x['dt'].date(), not x['is_live'], x['dt'].time()))

            seen_matches = set()
            final_list = []
            title_tracker = {}

            for p_item in parsed_items:
                if p_item['match_url'] in seen_matches:
                    continue
                seen_matches.add(p_item['match_url'])

                raw_t = p_item['title']
                if raw_t in title_tracker:
                    title_tracker[raw_t] += 1
                    p_item['title'] = f"{raw_t} (SV{title_tracker[raw_t]})"
                else:
                    title_tracker[raw_t] = 1

                final_list.append(p_item)

        except Exception as e:
            print(f"[!] Lỗi kết nối: {e}")
        finally:
            browser.close()

    # Ghi file M3U Playlist
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write('#EXTM3U tvg-shift="0"\n\n')
        for item in final_list:
            logo_attr = f'tvg-logo="{item["logo"]}"' if item["logo"] else ''
            
            full_playable_url = f"{item['stream_url']}|User-Agent={USER_AGENT}&Referer={REFERRER_HEADER}"
            
            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}",{item["title"]}\n')
            f.write(f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n')
            f.write(f'#EXTVLCOPT:http-referrer={REFERRER_HEADER}\n')
            f.write(f'{full_playable_url}\n\n')

    print(f"[*] Xuất thành công {len(final_list)} trận vào file {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
