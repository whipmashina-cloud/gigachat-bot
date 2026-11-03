import os
import csv
import io
import json
import time
import uuid
import requests

# --- Путь к файлу сертификатов ---
# Получаем абсолютный путь к файлу cacert.pem, который лежит рядом со скриптом.
CERT_FILE_PATH = os.path.join(os.path.dirname(__file__), 'cacert.pem')
# --- Конец настройки ---

import urllib3
from flask import Flask, request, jsonify, render_template

# Отключаем предупреждения urllib3 для внутреннего API Сбера
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# Получаем настройки из окружения
GIGACHAT_AUTH_KEY = os.environ.get("GIGACHAT_AUTH_KEY")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "115oOjWSwkFUuZnBomimcbvPsf_c6cyqmbgrFwyFSVE")

# Настройки GID листов
SHEET_GIDS = {
    "all": ["1202844813"],
    "goods": ["1202844813"]
}

# --- ПАРАМЕТРЫ КЭШИРОВАНИЯ И ТАЙМАУТОВ ---
CACHE_TIMEOUT = 300
GIGACHAT_TOKEN_TIMEOUT = 15
SHEET_FETCH_TIMEOUT = 20
GIGACHAT_API_TIMEOUT = 25

DATA_CACHE = {"data": None, "timestamp": 0}


def get_gigachat_token():
    print("=== НАЧАЛО ЗАПРОСА ТОКЕНА GIGACHAT ===")
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    payload = 'scope=GIGACHAT_API_PERS'
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RQUID': str(uuid.uuid4()),
        'Authorization': f'Basic {GIGACHAT_AUTH_KEY}'
    }
    
    try:
        # Для Сбер ID используем verify=False
        response = requests.post(url, headers=headers, data=payload, verify=False, timeout=GIGACHAT_TOKEN_TIMEOUT)
        print(f"Token status code: {response.status_code}")
        if response.status_code == 200:
            return response.json().get('access_token')
        else:
            print(f"Token error response: {response.text}")
    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА запроса токена: {e}")
    print("=== КОНЕЦ ЗАПРОСА ТОКЕНА ===")
    return None


def fetch_sheet_data(gid):
    url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={gid}"
    try:
        # Для Google Sheets используем наш файл сертификатов
        response = requests.get(url, timeout=SHEET_FETCH_TIMEOUT, verify=CERT_FILE_PATH)
        if response.status_code == 200:
            return response.content.decode('utf-8')
        else:
            print(f"Google Sheets API returned status: {response.status_code} for gid: {gid}")
    except Exception as e:
        print(f"Error fetching sheet {gid}: {e}")
    return ""


def get_combined_warehouse_data(mode="all"):
    current_time = time.time()
    if DATA_CACHE["data"] and (current_time - DATA_CACHE["timestamp"] < CACHE_TIMEOUT):
        return DATA_CACHE["data"]

    print("Кэш просрочен или пуст. Пытаемся обновить данные склада...")
    
    gids = SHEET_GIDS.get(mode, SHEET_GIDS["all"])
    combined_data = []
    header = None
    
    for gid in gids:
        csv_data = fetch_sheet_data(gid)
        if not csv_data:
            continue
            
        f = io.StringIO(csv_data)
        reader = csv.reader(f)
        rows = list(reader)
        if not rows:
            continue
            
        if not header:
            header = rows[0]
            combined_data.append(header)
            
        combined_data.extend(rows[1:])
        
    if not header:
        if DATA_CACHE["data"]:
            return DATA_CACHE["data"]
        return "Не удалось загрузить данные склада."
        
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(combined_data)
    result = output.getvalue()

    DATA_CACHE["data"] = result
    DATA_CACHE["timestamp"] = current_time
    print("Данные склада успешно обновлены в кэше.")
    return result


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.json or {}
    user_message = data.get('message', '').strip()
    
    if not user_message:
        return jsonify({'reply': 'Пустое сообщение.'}), 400

    if not GIGACHAT_AUTH_KEY:
        return jsonify({'reply': 'Ошибка: не задана переменная окружения GIGACHAT_AUTH_KEY.'}), 500

    token = get_gigachat_token()
    if not token:
        return jsonify({'reply': 'Ошибка авторизации в GigaChat API. Проверьте ключ.'}), 500

    warehouse_data = get_combined_warehouse_data("all")

    url = "https://api.giga.chat/v1/chat/completions"
    payload = json.dumps({
        "model": "GigaChat-3-Ultra",
        "messages": [
            {
                "role": "system", 
                "content": f"Ты профессиональный помощник на складе. Вот актуальные данные из таблиц учета:\n{warehouse_data}\nОтвечай четко, по делу и опирайся строго на эти данные."
            },
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.3,
        "profanity_check": True
    })
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    try:
        # --- ГЛАВНОЕ ИЗМЕНЕНИЕ ЗДЕСЬ ---
        # Явно указываем путь к файлу сертификатов для запроса к GigaChat
        response = requests.post(url, headers=headers, data=payload, timeout=GIGACHAT_API_TIMEOUT, verify=CERT_FILE_PATH)
        # --- ---
        
        print(f"Chat status code: {response.status_code}")
        res_data = response.json()
        
        if response.status_code == 200 and 'choices' in res_data:
            reply = res_data['choices'][0]['message']['content']
            return jsonify({'reply': reply})
        else:
            err_msg = res_data.get('message', 'Неизвестная ошибка GigaChat')
            print(f"GigaChat Error: {res_data}")
            return jsonify({'reply': f'Ошибка от GigaChat: {err_msg}'})
            
    except Exception as e:
        print(f"Chat error: {str(e)}")
        return jsonify({'reply': f'Ошибка обращения к GigaChat: {str(e)}'})


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False) 
