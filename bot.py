import os
import csv
import io
import json
import time
import requests
import urllib3
from flask import Flask, request, jsonify, render_template

# Отключаем предупреждения о самоподписанных сертификатах Сбера
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# Получаем настройки из окружения (или используем дефолтные значения)
GIGACHAT_AUTH_KEY = os.environ.get("GIGACHAT_AUTH_KEY")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "115oOjWSwkFUuZnBomimcbvPsf_c6cyqmbgrFwyFSVE")

SHEET_GIDS = {
    "all": ["0", "1433962862", "1202844813"],
    "sheet1": ["0", "1433962862"],
    "goods": ["1202844813"]
}

# Кэш для данных склада, чтобы не дергать Google Таблицу на каждый запрос
DATA_CACHE = {"data": None, "timestamp": 0}
CACHE_TIMEOUT = 300  # Время жизни кэша в секундах (5 минут)

def get_gigachat_token():
    print("=== НАЧАЛО ЗАПРОСА ТОКЕНА GIGACHAT ===")
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    payload = 'scope=GIGACHAT_API_PERS'
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RQUID': '6f002237-3318-48b6-86716d006324',
        'Authorization': f'Basic {GIGACHAT_AUTH_KEY}'
    }
    
    try:
        response = requests.post(url, headers=headers, data=payload, verify=False, timeout=15)
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
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.content.decode('utf-8')
    except Exception as e:
        print(f"Error fetching sheet {gid}: {e}")
    return ""

def get_combined_warehouse_data(mode="all"):
    current_time = time.time()
    # Если кэш валиден, возвращаем его (снижаем нагрузку на Google Docs)
    if DATA_CACHE["data"] and (current_time - DATA_CACHE["timestamp"] < CACHE_TIMEOUT):
        return DATA_CACHE["data"]

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
        return DATA_CACHE["data"] or "Не удалось загрузить данные склада."
        
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(combined_data)
    result = output.getvalue()

    # Обновляем кэш
    DATA_CACHE["data"] = result
    DATA_CACHE["timestamp"] = current_time
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
        return jsonify({'reply': 'Ошибка: не задана переменная окружения GIGACHAT_AUTH_KEY в настройках сервиса.'}), 500

    token = get_gigachat_token()
    if not token:
        return jsonify({'reply': 'Ошибка авторизации в GigaChat API (не удалось получить токен). Проверьте ключ GIGACHAT_AUTH_KEY.'}), 500

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
        response = requests.post(url, headers=headers, data=payload, verify=False, timeout=25)
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
    app.run(host='0.0.0.0', port=port, debug=True)
