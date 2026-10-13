import os
import csv
import io
import requests
from flask import Flask, request, render_template_string, Response

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
        'Authorization': f'Bearer {GIGACHAT_AUTH_KEY}'
    }
    try:
        response = requests.post(url, headers=headers, data=payload, verify=False, timeout=10)
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
        # Добавляем строки данных без повтора заголовков
        combined_data.extend(rows[1:])
        
    if not header:
        return "Не удалось загрузить данные склада."
        
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(combined_data)
    return output.getvalue()

# --- ВАШ ВЕБ-ИНТЕРФЕЙС СО ВСТРОЕННЫМ ГОЛОСОВЫМ ПОМОЩНИКОМ ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Склад AI — Голосовой помощник</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #f4f6f9;
            margin: 0;
            padding: 20px;
            display: flex;
            justify-content: center;
        }
        .container {
            width: 100%;
            max-width: 700px;
            background: #ffffff;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }
        h2 { text-align: center; color: #333; margin-top: 0; }
        #chat-box {
            height: 420px;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            overflow-y: auto;
            background: #fafafa;
            margin-bottom: 15px;
            font-size: 14px;
        }
        .message {
            margin-bottom: 12px;
            padding: 10px 14px;
            border-radius: 8px;
            line-height: 1.4;
            white-space: pre-wrap;
        }
        .message.user { background: #e3f2fd; text-align: right; }
        .message.ai { background: #e8f5e9; text-align: left; }
        .controls {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        input[type="text"] {
            flex: 1;
            padding: 12px;
            border: 1px solid #ccc;
            border-radius: 6px;
            font-size: 16px;
        }
        button {
            padding: 12px 18px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 16px;
            color: #fff;
            background: #007bff;
            transition: background 0.2s;
        }
        button:hover { background: #0056b3; }
        #mic-btn {
            background: #28a745;
            font-size: 18px;
            padding: 12px 16px;
        }
        #mic-btn.recording {
            background: #dc3545;
            animation: pulse 1.5s infinite;
        }
        #voice-status {
            font-size: 12px;
            color: #666;
            margin-top: 6px;
            text-align: center;
        }
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.05); }
            100% { transform: scale(1); }
        }
    </style>
</head>
<body>

<div class="container">
    <h2>📦 Склад AI — Управление складом</h2>
    
    <div id="chat-box">
        <div class="message ai"><strong>Система:</strong><br>Привет! Задайте вопрос текстом или нажмите кнопку микрофона для голосового поиска.</div>
    </div>
    
    <div id="voice-status">Готов к работе.</div>

    <div class="controls" style="margin-top: 10px;">
        <input type="text" id="user-input" placeholder="Введите наименование детали или артикул...">
        <button id="mic-btn" title="Голосовой ввод">🎤</button>
        <button id="send-btn">Найти</button>
    </div>
</div>

<script>
    const chatBox = document.getElementById('chat-box');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const micBtn = document.getElementById('mic-btn');
    const voiceStatus = document.getElementById('voice-status');

    // Настройка Web Speech API (Распознавание речи)
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition = null;

    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.lang = 'ru-RU';
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;

        recognition.onstart = () => {
            voiceStatus.textContent = "🎤 Слушаю вас... Говорите запрос.";
            micBtn.classList.add('recording');
        };

        recognition.onresult = (event) => {
            const speechText = event.results[0][0].transcript;
            userInput.value = speechText;
            voiceStatus.textContent = `✅ Распознано: "${speechText}"`;
            micBtn.classList.remove('recording');
            sendMessage(); // Автоматическая отправка запроса после голоса
        };

        recognition.onerror = (event) => {
            voiceStatus.textContent = `❌ Ошибка микрофона: ${event.error}`;
            micBtn.classList.remove('recording');
        };

        recognition.onend = () => {
            micBtn.classList.remove('recording');
        };
    } else {
        voiceStatus.textContent = "⚠️ Голосовой ввод не поддерживается вашим браузером (рекомендуется Chrome).";
        micBtn.style.display = 'none';
    }

    micBtn.addEventListener('click', () => {
        if (recognition) {
            try {
                recognition.start();
            } catch (e) {
                console.error(e);
            }
        }
    });

    // Функция синтеза речи (Озвучка ответа бота)
    function speakText(text) {
        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
            const cleanText = text.replace(/<[^>]*>?/gm, ''); // Очистка от HTML-тегов
            const utterance = new SpeechSynthesisUtterance(cleanText);
            utterance.lang = 'ru-RU';
            utterance.rate = 1.0;
            window.speechSynthesis.speak(utterance);
        }
    }

    // Отправка запроса на бэкенд
    async function sendMessage() {
        const text = userInput.value.trim();
        if (!text) return;

        appendMessage('Вы', text, 'user');
        userInput.value = '';
        voiceStatus.textContent = "Ищем данные...";

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text })
            });
            const data = await response.json();
            
            const reply = data.reply || "Нет ответа.";
            appendMessage('Склад AI', reply, 'ai');
            voiceStatus.textContent = "Готово.";
            
            // Озвучиваем ответ голосом
            speakText(reply);
        } catch (error) {
            appendMessage('Система', 'Ошибка связи с сервером.', 'ai');
            voiceStatus.textContent = "Ошибка сети.";
        }
    }

    sendBtn.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    function appendMessage(sender, text, className) {
        const div = document.createElement('div');
        div.className = `message ${className}`;
        div.innerHTML = `<strong>${sender}:</strong><br>${text}`;
        chatBox.appendChild(div);
        chatBox.scrollTop = chatBox.scrollHeight;
    }
</script>

</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.json
    user_message = data.get('message', '')
    
    token = get_gigachat_token()
    if not token:
        return {'reply': 'Ошибка авторизации в GigaChat API.'}

    # Подтягиваем данные из Google Таблиц
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
        res_data = response.json()
        reply = res_data['choices'][0]['message']['content']
        return {'reply': reply}
    except Exception as e:
        return {'reply': f'Ошибка обращения к GigaChat: {str(e)}'}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
