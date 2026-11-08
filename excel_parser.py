import logging
from datetime import datetime, timedelta
from io import BytesIO

from openpyxl import load_workbook

log = logging.getLogger("rhythm.excel")


def parse_excel_schedule(file_bytes: bytes) -> dict:
    wb = load_workbook(filename=BytesIO(file_bytes), data_only=True)
    ws = wb.active

    schedule_data = {}
    current_day = None
    class_cols = {}
    
    start_time = datetime.strptime("08:00", "%H:%M")
    days_map = {
        "Понедельник": 0,
        "Вторник": 1,
        "Среда": 2,
        "Четверг": 3,
        "Пятница": 4,
        "Суббота": 5,
    }
    
    for row in ws.iter_rows(values_only=True):
        if not row or not row[0]:
            continue
        
        first_col = str(row[0]).strip()
        
        if first_col in days_map:
            current_day = days_map[first_col]
            class_cols = {}
            for col_idx, cell in enumerate(row):
                if col_idx == 0:
                    continue
                if cell:
                    class_name = str(cell).strip()
                    class_cols[col_idx] = class_name
            continue
            
        if current_day is not None and first_col.isdigit():
            lesson_num = int(first_col)
            lesson_time = (start_time + timedelta(minutes=45 * (lesson_num - 1))).strftime("%H:%M")
            
            for col_idx, class_name in class_cols.items():
                if col_idx >= len(row):
                    continue
                subject_raw = row[col_idx]
                if not subject_raw:
                    continue
                
                subject_text = str(subject_raw).strip()
                
                if "(" in subject_text and ")" in subject_text:
                    subject = subject_text.split("(")[0].strip()
                else:
                    subject = subject_text
                
                if "/" in subject:
                    subject = subject.split("/")[0].strip()
                    
                if not subject or subject == "None":
                    continue
                
                if class_name not in schedule_data:
                    schedule_data[class_name] = []
                
                schedule_data[class_name].append({
                    "day": current_day,
                    "time": lesson_time,
                    "subject": subject
                })
                
    return schedule_data