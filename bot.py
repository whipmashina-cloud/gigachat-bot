import os
import csv
import io
import requests
from flask import Flask, request
from duckduckgo_search import DDGS

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GIGACHAT_AUTH_KEY = os.environ.get("GIGACHAT_AUTH_KEY")

SPREADSHEET_ID = "115OqjWSWuKFUuZNBomimcbvPsf_c6cyqmBgrFWyFSVE"
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

def upload_image_to_gigachat(token, image_bytes):
    """Загружает файл изображения в хранилище GigaChat API и возвращает file_id"""
    url = "https://gigachat.devices.sberbank.ru/api/v1/files"
    headers = {
        'Authorization': f'Bearer {token}'
    }
    files = {
        'file': ('image.jpg', image_bytes, 'image/jpeg')
    }
    data = {
        'purpose': 'general'
    }
    try:
        response = requests.post(url, headers=headers, files=files, data=data, verify=False)
        if response.status_code == 200:
            res_json = response.json()
            file_id = res_json.get('id')
            print(f"Image uploaded successfully to GigaChat, file_id: {file_id}")
            return file_id
        else:
            print(f"Failed to upload image to GigaChat: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error uploading image: {e}")
    return None

def ask_gigachat(prompt, sheet_context, web_context, image_file_id=None):
    """Отправка запроса в GigaChat с поддержкой изображений через file_id"""
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
        "Внимательно анализируй прикрепленные изображения деталей, узлов или шильдиков, а также текстовый запрос. "
        "Используй данные из внутренней базы Google Таблицы и интернета, чтобы точно идентифицировать деталь, "
        "описать её характеристики, предложить аналоги и указать место хранения на складе, если она есть в базе."
    )
    
    combined_context = ""
    if sheet_context:
        combined_context += f"{sheet_context}\n\n"
    if web_context:
        combined_context += f"{web_context}\n\n"
        
    user_text = f"{combined_context}Запрос пользователя: {prompt if prompt else 'Что изображено на фото? Распознай деталь, опиши её и дай техническую справку.'}"

    user_message = {
        "role": "user",
        "content": user_text
    }
    
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
        print(f"GigaChat response status: {response.status_code}")
        
        if 'choices' in res_data and len(res_data['choices']) > 0:
            return res_data['choices'][0]['message']['content']
        else:
            print(f"Unexpected GigaChat response: {res_data}")
            return "Не удалось получить ответ от модели GigaChat."
    except Exception as e:
        print(f"GigaChat error: {e}")
        return "Произошла ошибка при обращении к GigaChat."

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if data and 'message' in data:
        message = data['message']
        chat_id = message['chat']['id']
        
        text =
