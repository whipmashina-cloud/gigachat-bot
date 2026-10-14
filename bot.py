import os
import csv
import io
import requests
import urllib3

# Отключаем предупреждения о самоподписанных сертификатах Сбера
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__) if 'Flask' in globals() else None # страховка для импорта
from flask import Flask, request, render_template, Response

app = Flask(__name__)

GIGACHAT_AUTH_KEY = os.environ.get("GIGACHAT_AUTH_KEY")
SPREADSHEET_ID = "115oOjWSwkFUuZnBomimcbvPsf_c6cyqmbgrFwyFSVE"

SHEET_GIDS = {
    "all": ["0", "1433962862", "1202844813"],
    "sheet1": ["0", "1433962862"],
    "goods": ["1202844813"]
}

def get_gigachat_token():
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    payload = {'scope': 'GIGACHAT_API_PERS'}
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RQUID': '6f002237-3318-48b6-86716d006324',
        'Authorization': f'Basic {GIGACHAT_AUTH_KEY}'
    }
    try:
        response = requests.post(url, headers=headers, data=payload, verify=False, timeout=10)
        print(f"Token status code: {response.status_code}")
        print(f"Token response: {response.text}")
        if response.status_code == 200:
            return response.json().get('access_token')
    except Exception as e:
        print(f"Error getting token: {e}")
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
        return "Не удалось загрузить данные склада."
        
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(combined_data)
    return output.getvalue()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.json
    user_message = data.get('message', '')
    
    token = get_gigachat_token()
    if not token:
        return {'reply': 'Ошибка авторизации в GigaChat API (не удалось получить токен). Проверьте ключ GIGACHAT_AUTH_KEY.'}

    warehouse_data = get_combined_warehouse_data("all")

    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    payload = {
        "model": "GigaChat",
        "messages": [
            {
                "role": "system", 
                "content": f"Ты помощник на складе. Вот актуальные данные из таблиц:\n{warehouse_data}\nОтвечай четко и по делу на основе этих данных."
            },
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.3,
        "stream": False
    }
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    try:
        response = requests.post(url, headers=headers, json=payload, verify=False, timeout=20)
        print(f"Chat status code: {response.status_code}")
        res_data = response.json()
        reply = res_data['choices'][0]['message']['content']
        return {'reply': reply}
    except Exception as e:
        print(f"Chat error: {str(e)}")
        return {'reply': f'Ошибка обращения к GigaChat: {str(e)}'}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
