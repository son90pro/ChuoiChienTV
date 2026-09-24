import re
from urllib.parse import unquote

def parse_teams_from_url(url: str) -> str:
    """
    Trích xuất tên 2 đội bóng chính xác 100% từ đường dẫn (URL slug) Phà Lăng TV.
    VD: /truc-tiep/japan-vs-uruguay-318q66h8z4poqo9 -> Japan vs Uruguay
    """
    match = re.search(r'/truc-tiep/([^/?#]+)', url)
    if not match:
        return ""
    slug = match.group(1)
    
    parts = slug.split('-vs-')
    if len(parts) != 2:
        return ""
    
    team1_slug, team2_slug = parts[0], parts[1]
    
    # Loại bỏ chuỗi mã hash ngẫu nhiên ở cuối URL (VD: -318q66h8z4poqo9)
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
    return ""

def format_match_title(item: dict) -> str:
    """
    Định dạng tiêu đề hiển thị chuẩn trên IPTV:
    [Giờ [Ngày]] ⚽ [Đội A] vs [Đội B] [(TÊN BLV)] [geo]
    """
    url = item.get('url', '')
    raw_text = item.get('text', '')
    explicit_blv = item.get('blv', '').strip()
    
    # 1. Trích xuất tên 2 đội từ URL Slug
    teams_str = parse_teams_from_url(url)
    if not teams_str:
        teams_str = "Trận đấu Phà Lăng TV"

    # 2. Trích xuất Giờ & Ngày
    time_str = ""
    time_match = re.search(r'\b\d{1,2}[:h]\d{2}(?:\s+\d{1,2}/\d{1,2})?\b', raw_text, re.IGNORECASE)
    if time_match:
        time_str = time_match.group(0)

    # 3. Trích xuất tên BLV
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

    # 4. Ghép lại chuỗi hoàn chỉnh
    title_parts = []
    if time_str:
        title_parts.append(time_str)
    
    title_parts.append("⚽")
    title_parts.append(teams_str)
    
    if formatted_blv:
        title_parts.append(formatted_blv)
        
    title_parts.append("[geo]")

    return " ".join(title_parts)
    
