import os
import csv
import io
import requests
from flask import Flask, request, render_template_string
from duckduckgo_search import DDGS

app = Flask(__name__)

GIGACHAT_AUTH_KEY = os.environ.get("GIGACHAT_AUTH_KEY")
SPREADSHEET_ID = "115OqjWSWuKFUuZNBomimcbvPsf_c6cyqmBgrFWyFSVE"
SHEET_GIDS = ["0", "1433962862"]

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
    """Ищет информацию в интернете"""
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
    """Загружает изображение в GigaChat API"""
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

def ask_gigachat(prompt, sheet_context, web_context, image_file_id=None):
    """Отправка запроса в GigaChat"""
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
        "Анализируй запросы, изображения деталей, шильдиков, данные из таблиц и интернета. "
        "Выдавай точный технический ответ, характеристики, аналоги и места хранения."
    )
    
    combined_context = ""
    if sheet_context:
        combined_context += f"{sheet_context}\n\n"
    if web_context:
        combined_context += f"{web_context}\n\n"
        
    user_text = f"{combined_context}Запрос пользователя: {prompt if prompt else 'Распознай деталь на фото, опиши её и дай тех. справку.'}"

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

# HTML-интерфейс мобильного веб-приложения (PWA-чат)
CHAT_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Складской Помощник</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; margin: 0; padding: 0; display: flex; flex-direction: column; height: 100vh; }
        header { background: #1976d2; color: white; padding: 15px; text-align: center; font-size: 18px; font-weight: bold; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        #chat-container { flex: 1; overflow-y: auto; padding: 15px; display: flex; flex-direction: column; gap: 10px; }
        .message { max-width: 80%; padding: 12px 16px; border-radius: 12px; line-height: 1.4; word-break: break-word; white-space: pre-wrap; }
        .user { background: #dcf8c6; align-self: flex-end; border-bottom-right-radius: 2px; }
        .bot { background: white; align-self: flex-start; border-bottom-left-radius: 2px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); }
        #input-form { background: white; padding: 10px 15px; display: flex; gap: 10px; box-shadow: 0 -2px 5px rgba(0,0,0,0.05); align-items: center; }
        input[type="text"] { flex: 1; padding: 10px 14px; border: 1px solid #ccc; border-radius: 20px; outline: none; font-size: 16px; }
        input[type="file"] { display: none; }
        .file-btn { background: #e0e0e0; border: none; border-radius: 50%; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 18px; }
        button.send-btn { background: #1976d2; color: white; border: none; padding: 10px 20px; border-radius: 20px; font-weight: bold; cursor: pointer; }
        .loading { font-style: italic; color: #888; }
    </style>
</head>
<body>
    <header>🏭 AI Склад и Оборудование</header>
    <div id="chat-container">
        <div class="message bot">Здравствуйте! Я ваш инженерный помощник. Напишите запрос, артикул или прикрепите фото детали для анализа.</div>
    </div>
    <form id="input-form" onsubmit="sendMessage(event)">
        <label class="file-btn" title="Прикрепить фото">📷<input type="file" id="imageInput" accept="image/*"></label>
        <input type="text" id="messageInput" placeholder="Введите сообщение или название детали..." autocomplete="off">
        <button type="submit" class="send-btn">Отправить</button>
    </form>

    <script>
        async function sendMessage(e) {
            e.preventDefault();
            const msgInput = document.getElementById('messageInput');
            const imgInput = document.getElementById('imageInput');
            const container = document.getElementById('chat-container');

            const text = msgInput.value.trim();
            const file = imgInput.files;

            if (!text && file.length === 0) return;

            // Добавляем сообщение пользователя в чат
            const userDiv = document.createElement('div');
            userDiv.className = 'message user';
            userDiv.innerText = text + (file.length > 0 ? " [Прикреплено фото]" : "");
            container.appendChild(userDiv);

            const formData = new FormData();
            formData.append('text', text);
            if (file.length > 0) {
                formData.append('image', file);
            }

            msgInput.value = '';
            imgInput.value = '';
            container.scrollTop = container.scrollHeight;

            // Индикатор загрузки
            const loadDiv = document.createElement('div');
            loadDiv.className = 'message bot loading';
            loadDiv.innerText = 'Анализирую данные и таблицы... ⏳';
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
                errDiv.innerText = 'Ошибка соединения с сервером.';
                container.appendChild(errDiv);
            }
            container.scrollTop = container.scrollHeight;
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(CHAT_TEMPLATE)

@app.route('/api/chat', methods=['POST'])
def api_chat():
    text = request.form.get('text', '')
    image_file_id = None

    if 'image' in request.files:
        img_file = request.files['image']
        if img_file.filename != '':
            img_bytes = img_file.read()
            token = get_gigachat_token()
            if token:
                image_file_id = upload_image_to_gigachat(token, img_bytes)

    sheet_data = search_in_sheet(text) if text else ""
    web_data = search_web(text) if text else ""

    reply_text = ask_gigachat(text, sheet_data, web_data, image_file_id)
    return {'reply': reply_text}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
