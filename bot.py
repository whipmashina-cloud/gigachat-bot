import os
import csv
import io
import requests
from flask import Flask, request

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GIGACHAT_AUTH_KEY = os.environ.get("GIGACHAT_AUTH_KEY")

# Ссылка на правильную вкладку Google Таблицы в формате CSV
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/115OqjWSWuKFUuZNBomimcbvPsf_c6cyqmBgrFWyFSVE/export?format=csv&gid=1433962862"

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
    """Ищет совпадения по коду или ключевым словам в Google Таблице"""
    try:
        response = requests.get(SHEET_CSV_URL)
        if response.status_code != 200:
            print(f"Failed to fetch CSV, status code: {response.status_code}")
            return ""
        
        reader = csv.reader(io.StringIO(response.text))
        rows = list(reader)
        
        query_lower = query_text.lower().strip()
        matched_rows = []
        
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

def ask_gigachat(prompt, sheet_context):
    """Отправка запроса в GigaChat с учетом данных из таблицы и общих знаний"""
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
        "Ты профессиональный технический ассистент и инженер по оборудованию и складской логистике на производстве. "
        "Внимательно анализируй данные из внутренней базы 1С предприятия, переданные в запросе. Если позиция найдена в таблице, "
        "обязательно укажи её точные данные, склад и место хранения. Если данных в таблице нет или задан общий вопрос, "
        "используй свои инженерные знания, чтобы помочь подобрать аналоги, описать характеристики или дать техническую консультацию."
    )
    
    if sheet_context:
        user_content = f"{sheet_context}\n\nВопрос пользователя: {prompt}"
    else:
        user_content = f"Вопрос пользователя (во внутренней базе 1С точных совпадений по этому запросу не нашлось, отвечай на основе экспертных инженерных знаний): {prompt}"

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
            sheet_data = search_in_sheet(text)
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
    return "HELLO, HYBRID BOT!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
