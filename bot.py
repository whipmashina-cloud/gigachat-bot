import os
import csv
import io
import base64
import requests
from flask import Flask, request
from duckduckgo_search import DDGS

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GIGACHAT_AUTH_KEY = os.environ.get("GIGACHAT_AUTH_KEY")

# ID вашей Google Таблицы
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

def get_telegram_file_base64(file_id):
    """Скачивает файл из Telegram по file_id и кодирует в Base64"""
    try:
        # 1. Получаем путь к файлу у серверов Telegram
        file_info_url = f"{TELEGRAM_API_URL}/getFile?file_id={file_id}"
        r = requests.get(file_info_url).json()
        if not r.get("ok"):
            return None
        file_path = r["result"]["file_path"]
        
        # 2. Скачиваем сам файл
        download_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        file_response = requests.get(download_url)
        if file_response.status_code == 200:
            # 3. Переводим в base64 строку для GigaChat
            encoded = base64.b64encode(file_response.content).decode('utf-8')
            return encoded
    except Exception as e:
        print(f"Error downloading photo from telegram: {e}")
    return None

def ask_gigachat(prompt, sheet_context, web_context, image_base64=None):
    """Отправка запроса в GigaChat с поддержкой текста, контекста таблиц/сети и изображений"""
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
        "Анализируй присланные изображения (детали, узлы, маркировки, запчасти), а также данные из внутренней базы Google Таблицы "
        "и интернета. Помогай идентифицировать запчасти, определять их назначение, предлагать аналоги и указывать места хранения, если они есть в базе."
    )
    
    combined_context = ""
    if sheet_context:
        combined_context += f"{sheet_context}\n\n"
    if web_context:
        combined_context += f"{web_context}\n\n"
        
    user_text = f"{combined_context}Запрос пользователя: {prompt if prompt else 'Что изображено на фото? Определи деталь и её характеристики.'}"

    # Формируем структуру сообщения (если есть картинка, передаем её через attachments)
    user_message = {
        "role": "user",
        "content": user_text
    }
    
    if image_base64:
        user_message["attachments"] = [image_base64]

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
        return res_data['choices'][0]['message']['content']
    except Exception as e:
        print(f"GigaChat error: {e}")
        print(response.text if 'response' in locals() else "")
        return "Произошла ошибка при анализе изображения или запроса."

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if data and 'message' in data:
        message = data['message']
        chat_id = message['chat']['id']
        
        text = message.get('text', '') or message.get('caption', '') # Текст или подпись к фото
        image_base64 = None
        
        # Проверяем, есть ли в сообщении фотография
        if 'photo' in message:
            # Telegram присылает фото в нескольких размерах, берем последнее (самое качественное)
            photo_file_id = message['photo'][-1]['file_id']
            image_base64 = get_telegram_file_base64(photo_file_id)
            if not text:
                text = "Что это за деталь или узел? Распознай по фото."
        
        if text or image_base64:
            # Ищем в таблице по ключевым словам (если текст есть)
            sheet_data = search_in_sheet(text) if text else ""
            # Ищем в интернете
            web_data = search_web(text) if text else ""
            
            # Отправляем всё в GigaChat
            reply_text = ask_gigachat(text, sheet_data, web_data, image_base64)
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
    return "HELLO, MULTIMODAL HYBRID BOT!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
