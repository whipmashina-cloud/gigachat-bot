import os
import csv
import io
import requests
import urllib3
from flask import Flask, request, jsonify, render_template
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

# Отключаем предупреждения о сертификатах
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

GIGACHAT_AUTH_KEY = os.environ.get("GIGACHAT_AUTH_KEY")
SPREADSHEET_ID = "115oOjWSwkFUuZnBomimcbvPsf_c6cyqmbgrFwyFSVE"

SHEET_GIDS = {
    "all": ["0", "1433962862", "1202844813"],
    "sheet1": ["0", "1433962862"],
    "goods": ["1202844813"]
}

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
    data = request.json or {}
    user_message = data.get('message', '')
    
    if not user_message:
        return jsonify({'reply': 'Пустое сообщение.'}), 400

    warehouse_data = get_combined_warehouse_data("all")

    try:
        # Используем официальный SDK GigaChat с продвинутой моделью
        with GigaChat(
            credentials=GIGACHAT_AUTH_KEY,
            scope="GIGACHAT_API_PERS",
            verify_ssl_certs=False,
            model="GigaChat-Pro"  # Можно заменить на "GigaChat" или "GigaChat-Max"
        ) as giga:
            
            payload = Chat(
                messages=[
                    Messages(
                        role=MessagesRole.SYSTEM, 
                        content=f"Ты профессиональный помощник на складе. Вот актуальные данные из таблиц учета:\n{warehouse_data}\nОтвечай четко, по делу и опирайся строго на эти данные."
                    ),
                    Messages(role=MessagesRole.USER, content=user_message)
                ],
                temperature=0.3
            )
            
            response = giga.chat(payload)
            reply = response.choices[0].message.content
            return jsonify({'reply': reply})

    except Exception as e:
        print(f"GigaChat SDK error: {str(e)}")
        return jsonify({'reply': f'Ошибка обращения к GigaChat: {str(e)}'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
