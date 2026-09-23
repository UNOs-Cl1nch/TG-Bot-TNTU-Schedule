import requests
from bs4 import BeautifulSoup

def get_tntu_schedule(group_name="sb11", week=0):
    # Если week=0, грузится текущая неделя. Если 1 или 2 — конкретная.
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

    col_to_day_sub = {
        1: ("понеділок", 1), 2: ("понеділок", 2),
        3: ("вівторок", 0),
        4: ("середа", 0),
        5: ("четвер", 1), 6: ("четвер", 2),
        7: ("п'ятниця", 1), 8: ("п'ятниця", 2)
    }

    current_time = None
    rows = schedule_table.find_all('tr')

    for row in rows:
        cells = row.find_all(['th', 'td'])
        if not cells:
            continue

        time_cell = row.find('td', class_='LessonNumber')
        if time_cell:
            current_time = time_cell.get_text(separator=" ", strip=True)

        if "понеділок" in row.get_text():
            continue

        current_col_index = 1

        for cell in cells:
            if 'LessonNumber' in cell.get('class', []):
                continue

            colspan = int(cell.get('colspan', 1))
            col_info = col_to_day_sub.get(current_col_index)

            if col_info and current_time:
                day, subgroup = col_info
                if colspan > 1:
                    subgroup = 0

                if current_time not in schedule[day]:
                    schedule[day][current_time] = []

                subject_tag = cell.find('a')
                if subject_tag:
                    subject_name = subject_tag.get_text(strip=True)
                    subject_link = subject_tag.get('href', '')
                    full_text = cell.get_text(separator=" ", strip=True)
                    details = full_text.replace(subject_name, "").strip()

                    lesson_obj = {
                        "название": subject_name,
                        "ссылка": subject_link,
                        "детали": details,
                        "подгруппа": subgroup,
                        "пусто": False
                    }
                else:
                    lesson_obj = {"подгруппа": subgroup, "пусто": True}

                schedule[day][current_time].append(lesson_obj)

            current_col_index += colspan

    return schedule