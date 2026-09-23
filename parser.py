import requests
from bs4 import BeautifulSoup

def get_tntu_schedule(group_name="sb11", week=0):
    url = f'https://tntu.edu.ua/?p=uk/schedule&s=-{group_name}'
    if week > 0:
        url += f'&w={week}'

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return {"error": f"Помилка завантаження: {e}"}

    soup = BeautifulSoup(response.text, 'html.parser')
    schedule_table = soup.find('table', id='ScheduleWeek')

    if not schedule_table:
        return {"error": "Розклад не знайдено (можливо, невірна група)"}

    schedule = {
        "понеділок": {}, "вівторок": {}, "середа": {}, "четвер": {}, "п'ятниця": {}
    }

    rows = schedule_table.find_all('tr')
    grid = {}
    for row_idx, row in enumerate(rows):
        col_idx = 0
        for cell in row.find_all(['th', 'td']):
            while (row_idx, col_idx) in grid:
                col_idx += 1

            rowspan = int(cell.get('rowspan', 1))
            colspan = int(cell.get('colspan', 1))

            for r in range(rowspan):
                for c in range(colspan):
                    grid[(row_idx + r, col_idx + c)] = {
                        "cell": cell,
                        "is_primary": (r == 0 and c == 0),
                        "row_span": rowspan,
                        "col_span": colspan,
                        "text": cell.get_text(separator=" ", strip=True).lower()
                    }
            col_idx += colspan

    valid_days = ["понеділок", "вівторок", "середа", "четвер", "п'ятниця"]
    header_row_idx = None
    for (r, c), data in grid.items():
        if any(d in data["text"] for d in valid_days):
            header_row_idx = r
            break

    if header_row_idx is None:
        return {"error": "Не вдалося розпізнати структуру таблиці."}

    max_col = max(c for r, c in grid.keys())
    max_row = max(r for r, c in grid.keys())

    day_mapping = {}
    c = 1
    while c <= max_col:
        data = grid.get((header_row_idx, c))
        if data and data["is_primary"]:
            raw_name = data["text"]
            clean_name = next((d for d in valid_days if d in raw_name), None)
            if clean_name:
                colspan = data["col_span"]
                if colspan == 1:
                    day_mapping[c] = (clean_name, 0)
                else:
                    for i in range(colspan):
                        day_mapping[c + i] = (clean_name, i + 1)
                c += colspan
            else:
                c += 1
        else:
            c += 1

    current_time = None
    for row_idx in range(header_row_idx + 1, max_row + 1):
        time_data = grid.get((row_idx, 0))
        if time_data and time_data["is_primary"]:
            raw_time = time_data["cell"].get_text(separator=" ", strip=True)
            raw_time = raw_time.replace("- ", "-").replace(" -", "-")
            if raw_time:
                current_time = raw_time

        if not current_time:
            continue

        c = 1
        while c <= max_col:
            if c not in day_mapping:
                c += 1
                continue

            clean_name, expected_subgroup = day_mapping[c]
            data = grid.get((row_idx, c))

            if data:
                cell = data["cell"]
                colspan = data["col_span"]

                if current_time not in schedule[clean_name]:
                    schedule[clean_name][current_time] = []

                subgroup_to_assign = expected_subgroup
                if colspan > 1:
                    subgroup_to_assign = 0

                subject_tag = cell.find('a')
                if subject_tag:
                    subject_name = subject_tag.get_text(strip=True)
                    subject_link = subject_tag.get('href', '')
                    full_text = cell.get_text(separator=" ", strip=True)
                    details = full_text.replace(subject_name, "").strip()

                    schedule[clean_name][current_time].append({
                        "название": subject_name,
                        "ссылка": subject_link,
                        "детали": details,
                        "подгруппа": subgroup_to_assign,
                        "пусто": False
                    })
                else:
                    schedule[clean_name][current_time].append({
                        "подгруппа": subgroup_to_assign,
                        "пусто": True
                    })

                c += colspan
            else:
                c += 1

    return schedule