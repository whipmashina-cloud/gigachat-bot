import os
import csv
import io
import json
import time
import uuid
import requests
import urllib3
from flask import Flask, request, jsonify, render_template

# --- НАСТРОЙКИ ---
# Отключаем предупреждения urllib3, так как для Сбер ID будем отключать проверку SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# Получаем настройки из окружения
GIGACHAT_AUTH_KEY = os.environ.get("GIGACHAT_AUTH_KEY")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "115oOjWSwkFUuZnBomimcbvPsf_c6cyqmbgrFwyFSVE")

# Настройки GID листов
SHEET_GIDS = {
    "all": ["1202844813"],   # ID листа goods
    "goods": ["1202844813"]
}

# --- ПАРАМЕТРЫ КЭШИРОВАНИЯ И ТАЙМАУТОВ ---
CACHE_TIMEOUT = 300  # Время жизни кэша в секундах (5 минут)
GIGACHAT_TOKEN_TIMEOUT = 15  # Таймаут на запрос токена
SHEET_FETCH_TIMEOUT = 20     # Таймаут на запрос к Google Таблице
GIGACHAT_API_TIMEOUT = 25    # Таймаут на запрос к GigaChat API

# Кэш для данных склада
DATA_CACHE = {"data": None, "timestamp": 0}


def get_gigachat_token():
    """
    Получает токен для авторизации в GigaChat API.
    ВНИМАНИЕ: verify=False используется ТОЛЬКО для внутреннего API Сбера.
    """
    print("=== НАЧАЛО ЗАПРОСА ТОКЕНА GIGACHAT ===")
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    payload = 'scope=GIGACHAT_API_PERS'
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        # Генерируем уникальный ID для каждого запроса
        'RQUID': str(uuid.uuid4()),
        'Authorization': f'Basic {GIGACHAT_AUTH_KEY}'
    }
    
    try:
        # Отключаем SSL проверку только для этого внутреннего адреса
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
    """
    Загружает данные из Google Sheet по GID в формате CSV.
    """
    url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={gid}"
    try:
        response = requests.get(url, timeout=SHEET_FETCH_TIMEOUT)
        if response.status_code == 200:
            return response.content.decode('utf-8')
        else:
            print(f"Google Sheets API returned status: {response.status_code} for gid: {gid}")
    except Exception as e:
        print(f"Error fetching sheet {gid}: {e}")
    return ""


def get_combined_warehouse_data(mode="all"):
    """
    Собирает данные со всех листов, используя кэш.
    Если не удается обновить данные, возвращает старые из кэша.
    """
    current_time = time.time()
    
    # 1. Если кэш валиден, возвращаем его
    if DATA_CACHE["data"] and (current_time - DATA_CACHE["timestamp"] < CACHE_TIMEOUT):
        return DATA_CACHE["data"]

    print("Кэш просрочен или пуст. Пытаемся обновить данные склада...")
    
    gids = SHEET_GIDS.get(mode, SHEET_GIDS["all"])
    combined_data = []
    header = None
    
    for gid in gids:
        csv_data = fetch_sheet_data(gid)
        if not csv_data:
            print(f"Warning: Failed to fetch data for gid {gid}. Skipping.")
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
        
    # 2. Если не удалось собрать данные (даже без заголовка)
    if not header:
        print("CRITICAL: Failed to fetch any data from sheets.")
        # Возвращаем старый кэш, если он был, иначе сообщение об ошибке
        if DATA_CACHE["data"]:
            return DATA_CACHE["data"]
        return "Не удалось загрузить данные склада."
        
    # Собираем итоговый CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(combined_data)
    result = output.getvalue()

    # 3. ТОЛЬКО если всё успешно, обновляем кэш
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
        # Здесь verify=True по умолчанию, что БЕЗОПАСНО
        response = requests.post(url, headers=headers, data=payload, timeout=GIGACHAT_API_TIMEOUT)
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
    # debug=True лучше выключать на боевом сервере
    app.run(host='0.0.0.0', port=port, debug=False) 
