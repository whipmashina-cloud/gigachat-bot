import os
import csv
import io
import requests
from flask import Flask, request, render_template_string, Response

app = Flask(__name__)

GIGACHAT_AUTH_KEY = os.environ.get("GIGACHAT_AUTH_KEY")
SPREADSHEET_ID = "115OqjWSWuKFUuZNBomimcbvPsf_c6cyqmBgrFWyFSVE"
SHEET_GIDS = ["0", "1433962862"]

def get_gigachat_token():
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    payload = {'scope': 'GIGACHAT_API_PERS'}
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': '6f002237-3318-48b6-963a-86716d006324',
        'Authorization': f'Bearer {GIGACHAT_AUTH_KEY}'
    }
    try:
        response = requests.post(url, headers=headers, data=payload, verify=False)
        return response.json().get('access_token')
    except Exception as e:
        print(f"Error getting token: {e}")
        return None

def search_in_sheet(query_text):
    try:
        all_rows = []
        for g in SHEET_GIDS:
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
        for row in all_rows:
            row_str = " ".join(row).lower()
            if any(w in row_str for w in query_words):
                if row not in matched_rows:
                    matched_rows.append(row)
                    
        top_rows = matched_rows[:15]
        if not top_rows:
            return ""
            
        result_text = "Данные из внутренней базы Google Таблицы предприятия:\n"
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

def search_web(query_text):
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = [r['body'] for r in ddgs.text(query_text, max_results=3)]
        if results:
            return "Информация из интернета:\n" + "\n".join(f"- {res}" for res in results)
        return ""
    except Exception as e:
        print(f"Web search error: {e}")
        return ""

def upload_image_to_gigachat(token, image_bytes):
    url = "https://gigachat.devices.sberbank.ru/api/v1/files"
    headers = {'Authorization': f'Bearer {token}'}
    files = {'file': ('image.jpg', image_bytes, 'image/jpeg')}
    data = {'purpose': 'general'}
    try:
        response = requests.post(url, headers=headers, files=files, data=data, verify=False)
        if response.status_code == 200:
            return response.json().get('id')
    except Exception as e:
        print(f"Error uploading image: {e}")
    return None

def ask_gigachat(prompt, sheet_context, web_context, image_file_id=None):
    token = get_gigachat_token()
    if not token:
        return "Ошибка авторизации GigaChat."
        
    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    system_prompt = (
        "Ты главный инженер по оборудованию и складской логистике. "
        "Анализируй запросы, изображения деталей, шильдиков, данные из таблиц и интернета. "
        "Выдавай точный технический ответ, характеристики, аналоги и места хранения."
    )
    
    combined_context = ""
    if sheet_context:
        combined_context += f"{sheet_context}\n\n"
    if web_context:
        combined_context += f"{web_context}\n\n"
        
    user_text = f"{combined_context}Запрос пользователя: {prompt if prompt else 'Распознай деталь на фото, опиши её и дай тех. справку.'}"

    user_message = {"role": "user", "content": user_text}
    if image_file_id:
        user_message["attachments"] = [image_file_id]

    payload = {
        "model": "GigaChat",
        "messages": [
            {"role": "system", "content": system_prompt},
            user_message
        ],
        "temperature": 0.3,
        "max_tokens": 1200
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, verify=False)
        res_data = response.json()
        if 'choices' in res_data and len(res_data['choices']) > 0:
            return res_data['choices'][0]['message']['content']
        else:
            return f"Ошибка GigaChat API: {res_data}"
    except Exception as e:
        return f"Ошибка запроса: {str(e)}"

# Новый ультрасовременный интерфейс
CHAT_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#0f172a">
    <title>Склад AI</title>
    <style>
        :root {
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --accent: #38bdf8;
            --accent-gradient: linear-gradient(135deg, #38bdf8 0%, #3b82f6 100%);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --user-bubble: #1e3a8a;
            --bot-bubble: #1e293b;
            --border: #334155;
        }

        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-main);
            margin: 0; padding: 0;
            display: flex; flex-direction: column; height: 100vh;
        }

        header {
            background: rgba(30, 41, 59, 0.8);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border);
            padding: 14px 20px;
            display: flex; align-items: center; justify-content: space-between;
            position: sticky; top: 0; z-index: 10;
        }
        .logo-box { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 18px; }
        .logo-icon {
            width: 34px; height: 34px; background: var(--accent-gradient);
            border-radius: 10px; display: flex; align-items: center; justify-content: center;
            font-size: 18px; box-shadow: 0 0 12px rgba(56, 189, 248, 0.4);
        }
        .status-badge {
            background: rgba(3
