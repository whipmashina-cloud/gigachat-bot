def search_in_sheet(query_text):
    """Ищет совпадения по коду или ключевым словам в Google Таблице"""
    try:
        response = requests.get(SHEET_CSV_URL)
        if response.status_code != 200:
            return ""
        
        reader = csv.reader(io.StringIO(response.text))
        rows = list(reader)
        
        query_lower = query_text.lower().strip()
        matched_rows = []
        
        # Сначала ищем точное совпадение по коду (колонка 0) или названию (колонка 1)
        for row in rows[1:]:
            code = row[0].lower().strip() if len(row) > 0 else ""
            name = row[1].lower().strip() if len(row) > 1 else ""
            row_str = " ".join(row).lower()
            
            if (query_lower in code) or (query_lower in name) or (query_lower in row_str):
                matched_rows.append(row)
                if len(matched_rows) >= 5:
                    break
                    
        if not matched_rows:
            return ""
            
        result_text = "Найденные позиции во внутренней базе 1С предприятия:\n"
        for r in matched_rows:
            code = r[0] if len(r) > 0 else ""
            name = r[1] if len(r) > 1 else ""
            equipment = r[2] if len(r) > 2 else ""
            warehouse = r[3] if len(r) > 3 else ""
            place = r[4] if len(r) > 4 else ""
            desc = r[5] if len(r) > 5 else ""
            status = r[6] if len(r) > 6 else ""
            result_text += f"• Код: {code} | Название: {name} | Оборудование: {equipment} | Склад: {warehouse} ({place}) | Описание: {desc} | Статус: {status}\n"
            
        return result_text
    except Exception as e:
        print(f"Error reading sheet: {e}")
        return ""
