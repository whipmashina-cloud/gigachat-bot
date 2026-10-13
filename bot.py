import os
import csv
import io
import requests
from flask import Flask, request, render_template_string, Response

app = Flask(__name__)

GIGACHAT_AUTH_KEY = os.environ.get("GIGACHAT_AUTH_KEY")
SPREADSHEET_ID = "115OqjWSWuKFUuZNBomimcbvPsf_c6cyqmBgrFWyFSVE"
# Маппинг складов на GID листов Google Таблицы
SHEET_GIDS = {
    "all": ["0", "1433962862"],
    "wh1": ["0"],
    "wh2": ["1433962862"]
}

def get_gigachat_token():
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

def search_in_sheet(query_text, warehouse_filter="all"):
    try:
        all_rows = []
        gids_to_search = SHEET_GIDS.get(warehouse_filter, SHEET_GIDS["all"])
        
        for g in gids_to_search:
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
                    
        top_rows = matched_rows[:12]
        if not top_rows:
            return ""
            
        result_text = "Найденные позиции из базы данных предприятия:\n"
        for r in top_rows:
            # Собираем все заполненные ячейки строки автоматически, чтобы не терять данные
            clean_cells = [cell.strip() for cell in r if cell.strip()]
            if clean_cells:
                result_text += f"• " + " | ".join(clean_cells) + "\n"
            
        return result_text
    except Exception as e:
        print(f"Error reading sheets: {e}")
        return ""

def search_web(query_text):
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = [r['body'] for r in ddgs.text(query_text, max_results=3)]
        if results:
            return "Информация из интернета:\n" + "\n".join(f"- {res}" for res in results)
        return ""
    except Exception as e:
        print(f"Web search error: {e}")
        return ""

def upload_image_to_gigachat(token, image_bytes):
    url = "https://gigachat.devices.sberbank.ru/api/v1/files"
    headers = {'Authorization': f'Bearer {token}'}
    files = {'file': ('image.jpg', image_bytes, 'image/jpeg')}
    data = {'purpose': 'general'}
    try:
        response = requests.post(url, headers=headers, files=files, data=data, verify=False)
        if response.status_code == 200:
            return response.json().get('id')
    except Exception as e:
        print(f"Error uploading image: {e}")
    return None

def ask_gigachat(prompt, sheet_context, web_context, image_file_id=None, mode="search", warehouse="all"):
    token = get_gigachat_token()
    if not token:
        return "Ошибка авторизации GigaChat."
        
    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    wh_names = {"all": "Все склады", "wh1": "Склад №1 (Детали)", "wh2": "Склад №2 (Оборудование)"}
    selected_wh = wh_names.get(warehouse, "Все склады")

    mode_instructions = {
        "search": "Режим: Поиск остатков. Выдавай полную информацию из таблиц (наименования, артикулы, оборудование, ячейки хранения).",
        "scan": "Режим: Сканирование шильдика/детали. Сфокусируйся на распознавании маркировок и сопоставлении с позициями базы.",
        "analog": "Режим: Подбор аналогов. Предложи взаимозаменяемые позиции."
    }

    system_prompt = (
        f"Ты главный инженер по оборудованию и складской логистике. Выбран склад: '{selected_wh}'. "
        f"{mode_instructions.get(mode, '')} "
        "Анализируй запросы, изображения, данные из таблиц и интернета. Выдавай развёрнутые и понятные ответы."
    )
    
    combined_context = ""
    if sheet_context:
        combined_context += f"{sheet_context}\n\n"
    if web_context:
        combined_context += f"{web_context}\n\n"
        
    user_text = f"{combined_context}Запрос пользователя: {prompt if prompt else 'Обработай фото и дай справку.'}"

    user_message = {"role": "user", "content": user_text}
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
        if 'choices' in res_data and len(res_data['choices']) > 0:
            return res_data['choices'][0]['message']['content']
        else:
            return f"Ошибка GigaChat API: {res_data}"
    except Exception as e:
        return f"Ошибка запроса: {str(e)}"

# PWA Шаблон интерфейса
CHAT_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#0f172a">
    <title>Склад AI</title>
    <style>
        :root {
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --accent: #38bdf8;
            --accent-gradient: linear-gradient(135deg, #38bdf8 0%, #3b82f6 100%);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --user-bubble: #1e3a8a;
            --bot-bubble: #1e293b;
            --border: #334155;
        }

        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg-primary); color: var(--text-main);
            margin: 0; padding: 0; display: flex; flex-direction: column; height: 100vh;
        }

        header {
            background: rgba(30, 41, 59, 0.95); backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border); padding: 12px 16px;
            display: flex; flex-direction: column; gap: 10px;
            position: sticky; top: 0; z-index: 10;
        }
        .header-top { display: flex; align-items: center; justify-content: space-between; }
        .logo-box { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 18px; }
        .logo-icon {
            width: 34px; height: 34px; background: var(--accent-gradient);
            border-radius: 10px; display: flex; align-items: center; justify-content: center;
            font-size: 18px; box-shadow: 0 0 12px rgba(56, 189, 248, 0.4);
        }
        
        .controls-bar { display: flex; gap: 8px; width: 100%; }
        select {
            background: var(--bg-primary); color: var(--text-main);
            border: 1px solid var(--border); border-radius: 10px;
            padding: 8px 12px; font-size: 13px; outline: none; flex: 1;
        }

        #chat-container {
            flex: 1; overflow-y: auto; padding: 16px;
            display: flex; flex-direction: column; gap: 14px; scroll-behavior: smooth;
        }

        .message {
            max-width: 88%; padding: 14px 18px; border-radius: 18px;
            font-size: 15px; line-height: 1.5; word-break: break-word; white-space: pre-wrap;
            animation: fadeIn 0.25s ease-out forwards;
        }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

        .user {
            background: var(--user-bubble); color: #fff; align-self: flex-end;
            border-bottom-right-radius: 4px; border: 1px solid rgba(59, 130, 246, 0.4);
        }
        .bot {
            background: var(--bot-bubble); color: var(--text-main); align-self: flex-start;
            border-bottom-left-radius: 4px; border: 1px solid var(--border);
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }

        .quick-actions {
            display: flex; gap: 8px; overflow-x: auto; padding: 8px 16px;
            background: var(--bg-primary); border-top: 1px solid rgba(255,255,255,0.05);
            scrollbar-width: none;
        }
        .quick-actions::-webkit-scrollbar { display: none; }
        .chip {
            background: var(--bg-secondary); color: var(--text-muted);
            border: 1px solid var(--border); border-radius: 20px;
            padding: 6px 14px; font-size: 13px; white-space: nowrap; cursor: pointer;
            transition: all 0.2s;
        }
        .chip:active { background: var(--accent); color: #fff; transform: scale(0.95); }

        .preview-area {
            display: none; padding: 8px 16px; background: var(--bg-secondary);
            border-top: 1px solid var(--border); align-items: center; gap: 12px;
        }
        .preview-img { width: 50px; height: 50px; border-radius: 8px; object-fit: cover; border: 1px solid var(--accent); }
        .remove-img { color: #ef4444; font-weight: bold; cursor: pointer; font-size: 14px; }

        #input-form {
            background: var(--bg-secondary); padding: 10px 14px;
            display: flex; gap: 10px; align-items: center; border-top: 1px solid var(--border);
        }
        .icon-btn {
            background: rgba(255,255,255,0.05); border: 1px solid var(--border);
            border-radius: 12px; width: 44px; height: 44px;
            display: flex; align-items: center; justify-content: center;
            cursor: pointer; font-size: 20px; color: var(--text-main); transition: 0.2s;
        }
        .icon-btn:active { transform: scale(0.92); background: rgba(255,255,255,0.1); }
        input[type="file"] { display: none; }

        input[type="text"] {
            flex: 1; background: var(--bg-primary); border: 1px solid var(--border);
            color: #fff; padding: 12px 16px; border-radius: 14px; outline: none; font-size: 15px;
        }
        input[type="text"]:focus { border-color: var(--accent); }

        .send-btn {
            background: var(--accent-gradient); border: none; color: white;
            border-radius: 14px; width: 44px; height: 44px; font-size: 18px;
            display: flex; align-items: center; justify-content: center; cursor: pointer;
            box-shadow: 0 0 10px rgba(56, 189, 248, 0.3);
        }
        .send-btn:active { transform: scale(0.92); }

        .loading-pulse { display: inline-block; animation: pulse 1.5s infinite; color: var(--accent); }
        @keyframes pulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
    </style>
</head>
<body>

    <header>
        <div class="header-top">
            <div class="logo-box">
                <div class="logo-icon">📦</div>
                <span>Склад AI</span>
            </div>
            <span style="font-size: 12px; color: #4ade80;">● Онлайн</span>
        </div>
        <div class="controls-bar">
            <select id="warehouseSelect">
                <option value="all">🏢 Все склады</option>
                <option value="wh1">📦 Склад №1</option>
                <option value="wh2">⚙️ Склад №2</option>
            </select>
            <select id="modeSelect">
                <option value="search">🔎 Поиск</option>
                <option value="scan">📷 Сканер</option>
                <option value="analog">🛠️ Аналоги</option>
            </select>
        </div>
    </header>

    <div id="chat-container">
        <div class="message bot">👋 Приветствую! Выберите склад и режим работы выше.\n\nЗадайте вопрос, укажите артикул или прикрепите фото.</div>
    </div>

    <div class="quick-actions">
        <div class="chip" onclick="quickSend('Где лежит подшипник?')">🔍 Где лежит деталь?</div>
        <div class="chip" onclick="quickSend('Проверь статус оборудования')">📋 Проверить статус</div>
        <div class="chip" onclick="quickSend('Подобрать аналог ремня')">🛠️ Подобрать аналоги</div>
    </div>

    <div class="preview-area" id="previewArea">
        <img id="previewImage" class="preview-img" src="" alt="preview">
        <span style="font-size: 13px; color: var(--text-muted);">Фото прикреплено</span>
        <span class="remove-img" onclick="clearImage()">Удалить</span>
    </div>

    <form id="input-form" onsubmit="sendMessage(event)">
        <label class="icon-btn" title="Сделать фото">
            📷 <input type="file" id="imageInput" accept="image/*" onchange="handleImageSelect(event)">
        </label>
        <input type="text" id="messageInput" placeholder="Артикул или наименование..." autocomplete="off">
        <button type="submit" class="send-btn">➔</button>
    </form>

    <script>
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/sw.js');
        }

        function handleImageSelect(e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(evt) {
                    document.getElementById('previewImage').src = evt.target.result;
                    document.getElementById('previewArea').style.display = 'flex';
                }
                reader.readAsDataURL(file);
            }
        }

        function clearImage() {
            document.getElementById('imageInput').value = '';
            document.getElementById('previewArea').style.display = 'none';
        }

        function quickSend(text) {
            document.getElementById('messageInput').value = text;
            sendMessage(new Event('submit'));
        }

        async function sendMessage(e) {
            e.preventDefault();
            const msgInput = document.getElementById('messageInput');
            const imgInput = document.getElementById('imageInput');
            const warehouse = document.getElementById('warehouseSelect').value;
            const mode = document.getElementById('modeSelect').value;
            const container = document.getElementById('chat-container');

            const text = msgInput.value.trim();
            const files = imgInput.files;

            if (!text && files.length === 0) return;

            const userDiv = document.createElement('div');
            userDiv.className = 'message user';
            userDiv.innerText = text + (files.length > 0 ? " [📷 Фото]" : "");
            container.appendChild(userDiv);

            const formData = new FormData();
            formData.append('text', text);
            formData.append('warehouse', warehouse);
            formData.append('mode', mode);

            if (files.length > 0) {
                formData.append('image', files[0]);
            }

            msgInput.value = '';
            clearImage();
            container.scrollTop = container.scrollHeight;

            const loadDiv = document.createElement('div');
            loadDiv.className.id = 'loadMsg';
            loadDiv.className = 'message bot';
            loadDiv.innerHTML = '<span class="loading-pulse">⚡ Анализирую базу и склад...</span>';
            container.appendChild(loadDiv);
            container.scrollTop = container.scrollHeight;

            try {
                const response = await fetch('/api/chat', { method: 'POST', body: formData });
                const data = await response.json();
                
                loadDiv.remove();

                const botDiv = document.createElement('div');
                botDiv.className = 'message bot';
                botDiv.innerText = data.reply;
                container.appendChild(botDiv);
            } catch (err) {
                loadDiv.remove();
                const errDiv = document.createElement('div');
                errDiv.className = 'message bot';
                errDiv.innerText = '⚠️ Ошибка связи с сервером.';
                container.appendChild(errDiv);
            }
            container.scrollTop = container.scrollHeight;
        }
    </script>
</body>
</html>
"""

MANIFEST_JSON = """{
  "name": "Склад AI",
  "short_name": "Склад AI",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0f172a",
  "theme_color": "#0f172a",
  "icons": [
    {
      "src": "https://cdn-icons-png.flaticon.com/512/3061/3061341.png",
      "sizes": "512x512",
      "type": "image/png"
    }
  ]
}"""

SERVICE_WORKER_JS = """
self.addEventListener('install', (e) => { self.skipWaiting(); });
self.addEventListener('fetch', (e) => { e.respondWith(fetch(e.request)); });
"""

@app.route('/')
def index():
    return render_template_string(CHAT_TEMPLATE)

@app.route('/manifest.json')
def manifest():
    return Response(MANIFEST_JSON, mimetype='application/json')

@app.route('/sw.js')
def service_worker():
    return Response(SERVICE_WORKER_JS, mimetype='application/javascript')

@app.route('/api/chat', methods=['POST'])
def api_chat():
    text = request.form.get('text', '')
    warehouse = request.form.get('warehouse', 'all')
    mode = request.form.get('mode', 'search')
    image_file_id = None

    if 'image' in request.files:
        img_file = request.files['image']
        if img_file.filename != '':
            img_bytes = img_file.read()
            token = get_gigachat_token()
            if token:
                image_file_id = upload_image_to_gigachat(token, img_bytes)

    sheet_data = search_in_sheet(text, warehouse) if text else ""
    web_data = search_web(text) if (text and mode == "analog") else ""

    reply_text = ask_gigachat(text, sheet_data, web_data, image_file_id, mode, warehouse)
    return {'reply': reply_text}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
