import re
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# Domain Chuối Chiến TV (hoặc đổi thành nguồn tương ứng)
BASE_URL = "https://chuoichientv1.link"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Referer": BASE_URL
}

def get_chuoi_chien_matches():
    matches = []
    # Lấy ngày hiện tại dạng DD/MM (ví dụ: 23/09)
    today_str = datetime.now().strftime("%d/%m")
    
    try:
        res = requests.get(BASE_URL, headers=HEADERS, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Lấy danh sách khung/card trận đấu trên web
        cards = soup.select('.match-item, .card-match, .item-match, div[class*="match"]')
        
        for card in cards:
            # 1. Bóc tách thời gian (Giờ:Phút)
            time_el = card.select_one('.time, .match-time, span[class*="time"]')
            time_str = time_el.get_text(strip=True) if time_el else "15:00"
            
            # 2. Bóc tách tên 2 đội
            team_els = card.select('.team-name, .name, .team, span[class*="team"]')
            if len(team_els) >= 2:
                team1 = team_els[0].get_text(strip=True)
                team2 = team_els[1].get_text(strip=True)
            else:
                full_text = card.get_text()
                match_vs = re.search(r'(.+?)\s+vs\s+(.+)', full_text, re.IGNORECASE)
                if match_vs:
                    team1, team2 = match_vs.group(1).strip(), match_vs.group(2).strip()
                else:
                    continue
            
            # 3. Bóc tách tên BLV (Bình luận viên)
            blv_el = card.select_one('.blv, .commentator, span[class*="blv"]')
            blv_name = blv_el.get_text(strip=True) if blv_el else "Chuối Chiến"
            blv_name = re.sub(r'^(BLV|Bình luận viên)\s*', '', blv_name, flags=re.IGNORECASE)
            
            # 4. Bóc tách Logo / Hình đại diện
            img_el = card.select_one('img')
            logo_url = img_el['src'] if (img_el and 'src' in img_el.attrs) else ""
            if logo_url and not logo_url.startswith('http'):
                logo_url = BASE_URL.rstrip('/') + '/' + logo_url.lstrip('/')
                
            # 5. Link luồng xem (M3U8 / HLS)
            link_el = card.select_one('a[href]')
            stream_url = link_el['href'] if link_el else "https://example.com/live.m3u8"
            
            # Chuẩn hóa tên tiêu đề kênh HỆT NHƯ TRONG ÁNH MẪU
            display_title = f"{time_str} {today_str} ⚽ {team1} vs {team2} ({blv_name}) [hls]"
            
            matches.append({
                "title": display_title,
                "team1": team1,
                "team2": team2,
                "time": f"{time_str} {today_str}",
                "blv": blv_name,
                "logo": logo_url,
                "url": stream_url
            })
            
    except Exception as e:
        print(f"Lỗi kết nối hoặc cào dữ liệu: {e}")
        
    return matches

def export_m3u(matches, group_name="Chuối Chiến TV"):
    """Xuất ra file M3U cho OTT Navigator / Tivimate / Monster TV"""
    m3u_content = ["#EXTM3U"]
    for m in matches:
        m3u_content.append(f'#EXTINF:-1 tvg-logo="{m["logo"]}" group-title="{group_name}",{m["title"]}')
        m3u_content.append(m["url"])
    return "\n".join(m3u_content)

# Run Script
if __name__ == "__main__":
    match_list = get_chuoi_chien_matches()
    
    # In ra Playlist M3U chuẩn
    m3u_result = export_m3u(match_list, group_name="Chuối Chiến TV")
    print(m3u_result)
    
    # Hoặc lưu ra file
    with open("chuoi_chien_tv.m3u", "w", encoding="utf-8") as f:
        f.write(m3u_result)
        
