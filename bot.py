import os
import requests
import gspread
from google.oauth2.service_account import Credentials
from flask import Flask, request

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GIGACHAT_AUTH_KEY = os.environ.get("GIGACHAT_AUTH_KEY")

# ID вашей Google Таблицы
SPREADSHEET_ID = "115OqjWSWuKFUuZNBomimcbvPsf_c6cyqmBgrFWyFSVE"

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

def search_in_google_sheet(query_text):
    """Ищет данные напрямую через публичный доступ Google Таблицы"""
    try:
        # Используем публичный экспорт CSV, но с точным парсингом колонок Google Таблицы
        csv_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid=0"
        response = requests.get(csv_url)
        if response.status_code != 200:
            return "Не удалось подключиться к Google Таблице."
        
        import csv
        import io
        reader = csv.reader(io.StringIO(response.text))
        rows = list(reader)
        
        query_lower = query_text.lower()
        matched_rows = []
        
        # Пропускаем шапку таблицы (строка 0)
        for row in rows[1:]:
            row_str = " ".join(row).lower()
            if any(word in row_str for word in query_lower.split()):
                matched_rows.append(row)
                if len(matched_rows) >= 5:
                    break
                    
        if not matched_rows:
            return "В Google Таблице по вашему запросу ничего не найдено."
            
        result_text = "Данные из Google Таблицы:\n"
        for r in matched_rows:
            code = r[0] if len(r) > 0 else ""
            name = r[1] if len(r) > 1 else ""
            equipment = r[2] if len(r) > 2 else ""
            warehouse = r[3] if len(r) > 3 else ""
            place = r[4] if len(r) > 4 else ""
            desc = r[5] if len(r) > 5 else ""
            status = r[6] if len(r) > 6 else ""
            result_text += f"• Код: {code} | Название: {name}\n  Оборудование: {equipment}\n  Склад: {warehouse} ({place})\n  Описание: {desc} | Статус: {status}\n\n"
            
        return result_text
    except Exception as e:
        print(f"Sheet error: {e}")
        return "Ошибка чтения Google Таблицы."

def ask_gigachat(prompt, sheet_context):
    """Отправка запроса в GigaChat с контекстом из Google Таблицы"""
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
        "Ты технический ассистент по оборудованию и складской логистике на производстве. "
        "Используй данные из официальной Google Таблицы предприятия, чтобы отвечать на вопросы, "
        "помогать подбирать аналоги запчастей, компонентов и указывать точные места хранения."
    )
    
    payload = {
        "model": "GigaChat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Информация из Google Таблицы:\n{sheet_context}\n\nВопрос пользователя: {prompt}"}
        ],
        "temperature": 0.3,
        "max_tokens": 1000
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
            sheet_data = search_in_google_sheet(text)
            reply_text = ask_gigachat(text, sheet_data)
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
    return "HELLO, GOOGLE SHEETS BOT!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
