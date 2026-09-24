import time
import re
from urllib.parse import quote
from playwright.sync_api import sync_playwright

WORKER_DOMAIN = "cctv.sonnguyen90pro.workers.dev"
BASE_URL = "https://phalang.tv"

OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Phá Làng TV"

EXCLUDE_KEYWORDS = [
    'lịch thi đấu', 'kết quả', 'tin tức', 'bảng xếp hạng', 'soi kèo',
    'nhà cái', 'đăng ký', 'đăng nhập', 'khuyến mãi', 'liên hệ', 'giới thiệu',
    'chính sách', 'hướng dẫn', 'tải app', 'privacy', 'terms'
]

def parse_teams_from_url(url: str) -> str:
    """Trích xuất tên 2 đội bóng chính xác từ URL slug"""
    try:
        match = re.search(r'/truc-tiep/([^/?#]+)', url)
        if not match:
            return ""
        slug = match.group(1)
        
        parts = slug.split('-vs-')
        if len(parts) != 2:
            return ""
        
        team1_slug, team2_slug = parts[0], parts[1]
        team2_slug = re.sub(r'-[a-z0-9]{8,35}$', '', team2_slug, flags=re.IGNORECASE)
        
        def clean_team_name(name_slug: str) -> str:
            words = name_slug.split('-')
            words_formatted = []
            for w in words:
                w_lower = w.lower()
                if w_lower in ['nu', 'nữ']:
                    words_formatted.append('Nữ')
                elif w_lower in ['nam']:
                    words_formatted.append('Nam')
                elif w_lower in ['u23', 'u21', 'u20', 'u19', 'u18', 'u17', 'u16', 'u15']:
                    words_formatted.append(w.upper())
                elif w_lower in ['ir', 'uae', 'usa', 'uk']:
                    words_formatted.append(w.upper())
                else:
                    words_formatted.append(w.capitalize())
            return ' '.join(words_formatted)
            
        t1 = clean_team_name(team1_slug)
        t2 = clean_team_name(team2_slug)
        
        if t1 and t2:
            return f"{t1} vs {t2}"
    except Exception:
        pass
    return ""

def clean_match_title(item: dict) -> str:
    url = item.get('url', '')
    raw_text = item.get('text', '')
    explicit_blv = item.get('blv', '').strip()
    
    # 1. Trích xuất tên 2 đội từ URL
    teams_str = parse_teams_from_url(url)
    if not teams_str:
        teams_str = "Trận đấu Phà Lăng TV"

    # 2. Trích xuất thời gian
    time_str = ""
    time_match = re.search(r'\b\d{1,2}[:h]\d{2}(?:\s+\d{1,2}/\d{1,2})?\b', raw_text, re.IGNORECASE)
    if time_match:
        time_str = time_match.group(0)

    # 3. Trích xuất tên BLV (nếu có)
    blv_str = explicit_blv
    if not blv_str:
        for line in raw_text.split('\n'):
            l_clean = line.strip()
            l_low = l_clean.lower()
            if any(k in l_low for k in ['blv', 'caster', 'bình luận']) or l_low.startswith('lý ') or l_low.startswith('ly '):
                if not re.search(r'\d{1,2}[:/]\d{2}', l_clean) and not re.search(r'\b(vs|v/s)\b', l_low):
                    blv_str = l_clean
                    break

    formatted_blv = ""
    if blv_str:
        clean_blv = re.sub(r'^(BLV|Caster|Bình luận viên|BLV:)\s*[:\-]?\s*', '', blv_str, flags=re.IGNORECASE).strip()
        clean_blv = clean_blv.strip('()[]{}')
        if clean_blv and not re.search(r'\d{1,2}[:/]\d{2}', clean_blv) and len(clean_blv) < 30:
            formatted_blv = f"({clean_blv.upper()})"

    # 4. Ghép tiêu đề hiển thị chuẩn
    parts = []
    if time_str:
        parts.append(time_str)
    
    parts.append("⚽")
    parts.append(teams_str)
    
    if formatted_blv:
        parts.append(formatted_blv)
        
    parts.append("[geo]")

    return " ".join(parts)

def is_valid_match_url(href, text):
    low_href = href.lower()
    low_text = text.lower()

    for kw in EXCLUDE_KEYWORDS:
        if kw in low_text or kw.replace(' ', '-') in low_href:
            return False

    if low_href.strip() in [BASE_URL.lower(), BASE_URL.lower() + "/", "#", "javascript:void(0)"]:
        return False

    if len(href) <= len(BASE_URL) + 2:
        return False

    return True

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
        for _ in range(10):
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
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        # Ép trình duyệt dùng múi giờ Việt Nam (Asia/Ho_Chi_Minh)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            timezone_id="Asia/Ho_Chi_Minh",
            locale="vi-VN"
        )

        final_matches = []
        page = context.new_page()

        try:
            print(f"[*] Đang tải trang Phà Lăng TV: {BASE_URL}")
            page.goto(BASE_URL, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)

            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            time.sleep(1.5)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)

            raw_matches = page.evaluate('''() => {
                const matches = [];
                const links = Array.from(document.querySelectorAll('a[href*="/truc-tiep/"]'));
                const seenUrls = new Set();

                for (const a of links) {
                    let href = a.href;
                    if (!href || seenUrls.has(href)) continue;
                    seenUrls.add(href);

                    let card = a.closest('.match-item, .card, .match-card, [class*="match"], [class*="card"]') || a.parentElement;
                    const text = card ? card.innerText : a.innerText;

                    let blv = '';
                    if (card) {
                        const blvEl = card.querySelector('[class*="blv"], [class*="caster"], [class*="commentator"], .author, .name');
                        if (blvEl) {
                            blv = blvEl.innerText.trim();
                        } else {
                            const lines = text.split('\\n');
                            for (let line of lines) {
                                line = line.trim();
                                if (/^(blv|caster|bình luận viên)\\b/i.test(line) || /^lý\\s+/i.test(line)) {
                                    blv = line;
                                    break;
                                }
                            }
                        }
                    }

                    let logo = '';
                    if (card) {
                        const img = card.querySelector('img');
                        if (img) {
                            let src = img.getAttribute('src') || img.getAttribute('data-src') || '';
                            if (src && !src.includes('favicon')) {
                                logo = src.startsWith('http') ? src : window.location.origin + src;
                            }
                        }
                    }

                    matches.push({
                        url: href,
                        text: text,
                        blv: blv,
                        logo: logo
                    });
                }
                return matches;
            }''')

            unique_matches = {}
            for item in raw_matches:
                url = item['url']

                if url in unique_matches:
                    continue

                if not is_valid_match_url(url, item['text']):
                    continue

                formatted_title = clean_match_title(item)

                unique_matches[url] = {
                    "title": formatted_title,
                    "logo": item['logo'],
                    "url": url
                }

            match_list = list(unique_matches.values())
            page.close()

            print(f"[*] Tìm thấy {len(match_list)} trận đấu trên Phà Lăng TV. Đang trích xuất link stream...")
            for idx, match in enumerate(match_list):
                print(f"[{idx+1}/{len(match_list)}] Lấy stream: {match['title']}")
                m3u8_url = get_m3u8_for_match(context, match['url'])
                match['m3u8_url'] = m3u8_url

            final_matches = match_list

        except Exception as e:
            print(f"[!] Lỗi khi cào dữ liệu: {e}")
            page.close()

        browser.close()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")

        for item in final_matches:
            logo_attr = f'tvg-logo="{item["logo"]}"' if item["logo"] else ''
            ref_url = BASE_URL

            if item.get('m3u8_url'):
                encoded_m3u8 = quote(item['m3u8_url'], safe='')
                encoded_ref = quote(ref_url, safe='')
                stream_url = f"https://{WORKER_DOMAIN}/proxy?url={encoded_m3u8}&referer={encoded_ref}"
            else:
                stream_url = f"https://{WORKER_DOMAIN}/proxy?url={quote(item['url'], safe='')}"
            
            f.write(f'#EXTINF:-1 {logo_attr} group-title="{GROUP_NAME}",{item["title"]}\n')
            f.write(f'{stream_url}\n\n')

    print(f"[*] Hoàn tất! Đã xuất {len(final_matches)} trận vào {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
