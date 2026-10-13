def search_in_sheet(query_text):
    """Скачивает все листы Google Таблицы и ищет совпадения по всей базе"""
    try:
        # Получаем список всех листов таблицы через стандартный экспорт метаданных или перебираем gid
        # Так как у нас публичная таблица, пройдем по известным gid или выкачаем главный экспорт
        # Но самый надежный способ для публичной таблицы — выкачать экспорт без gid (все листы разом в zip или первый лист)
        # Давайте сделаем универсальный сбор по основному CSV и дополнительным вкладкам
        
        gids = ["0", "1433962862"] # Ваши вкладки: Лист_1 и Пат_1 (можно дописать другие, если появятся)
        all_rows = []
        
        for g in gids:
            url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={g}"
            response = requests.get(url)
            if response.status_code == 200:
                reader = csv.reader(io.StringIO(response.text))
                rows = list(reader)
                all_rows.extend(rows)
                
        if not all_rows:
            return ""
            
        query_words = [w.lower().strip() for w in query_text.split() if len(w) > 1]
        if not query_words:
            query_words = [query_text.lower().strip()]
            
        matched_rows = []
        
        # Ищем по всем строкам со всех листов
        for row in all_rows:
            row_str = " ".join(row).lower()
            # Проверяем совпадение хотя бы одного слова или артикула
            if any(w in row_str for w in query_words):
                if row not in matched_rows:
                    matched_rows.append(row)
                    
        # Ограничим до 20 позиций для передачи в GigaChat
        top_rows = matched_rows[:20]
        
        if not top_rows:
            return ""
            
        result_text = "Данные из Google Таблицы (все вкладки предприятия):\n"
        for r in top_rows:
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
        print(f"Error reading sheets: {e}")
        return ""
