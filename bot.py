import os
import csv
import io
import requests
from flask import Flask, request
from duckduckgo_search import DDGS

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GIGACHAT_AUTH_KEY = os.environ.get("GIGACHAT_AUTH_KEY")

# ID вашей Google Таблицы
SPREADSHEET_ID = "115OqjWSWuKFUuZNBomimcbvPsf_c6cyqmBgrFWyFSVE"
# Список всех вкладок (gid), которые нужно опрашивать (Лист_1 и Пат_1)
SHEET_GIDS = ["0", "1433962862"]

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

def get_gigachat_token():
    """Получение токена доступа для GigaChat API"""
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
    """Ищет совпадения по всем вкладкам Google Таблицы"""
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
    """Ищет информацию и технические характеристики в интернете"""
    try:
        with DDGS() as ddgs:
            results = [r['body'] for r in ddgs.text(query_text, max_results=3)]
        if results:
            return "Информация из интернета:\n" + "\n".join(f"- {res}" for res in results)
        return ""
    except Exception as e:
        print(f"Web search error: {e}")
        return ""

def ask_gigachat(prompt, sheet_context, web_context):
    """Отправка запроса в GigaChat с контекстом из таблицы и интернета"""
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
        "Используй данные из внутренней базы Google Таблицы предприятия (если они найдены), чтобы подсказать точное место хранения, "
        "склад и статус детали. Также используй информацию из интернета (если она предоставлена), чтобы рассказать про технические характеристики, "
        "назначение детали или предложить надежные аналоги. Формируй четкие, профессиональные и полезные технические ответы."
    )
    
    combined_context = ""
    if sheet_context:
        combined_context += f"{sheet_context}\n\n"
    if web_context:
        combined_context += f"{web_context}\n\n"
        
    user_content = f"{combined_context}Запрос пользователя: {prompt}"

    payload = {
        "model": "GigaChat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.3,
        "max_tokens": 1200
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, verify=False)
        res_data = response.json()
        return res_data['choices'][0]['message']['content']
    except Exception as e:
        print(f"GigaChat error: {e}")
        return "Произошла ошибка при обращении к GigaChat."

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if data and 'message' in data:
        chat_id = data['message']['chat']['id']
        text = data['message'].get('text', '')
        
        if text:
            # 1. Ищем в Google Таблице (по всем вкладкам)
            sheet_data = search_in_sheet(text)
            # 2. Ищем в интернете
            web_data = search_web(text)
            # 3. Передаем всё в GigaChat
            reply_text = ask_gigachat(text, sheet_data, web_data)
            send_message(chat_id, reply_text)
            
    return 'ok', 200

def send_message(chat_id, text):
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text
    }
    requests.post(url, json=payload)

@app.route('/')
def index():
    return "HELLO, ULTIMATE HYBRID BOT!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
