import os
import uuid
import urllib3
import requests
from flask import Flask, request

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
AUTH_KEY = os.environ.get("GIGACHAT_AUTH_KEY")

def get_gigachat_token():
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RqUID': str(uuid.uuid4()),
        'Authorization': f'Basic {AUTH_KEY}'
    }
    try:
        res = requests.post(url, headers=headers, data={'scope': 'GIGACHAT_API_PERS'}, verify=False)
        return res.json().get("access_token")
    except Exception as e:
        print("Ошибка токена:", e)
        return None

def ask_gigachat(prompt):
    token = get_gigachat_token()
    if not token: 
        return "Ошибка авторизации в GigaChat"
    
    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    headers = {
        'Content-Type': 'application/json', 
        'Accept': 'application/json', 
        'Authorization': f'Bearer {token}'
    }
    payload = {
        "model": "GigaChat",
        "messages": [
            {"role": "system", "content": "Ты технический помощник на производстве. Отвечай кратко и по делу."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }
    try:
        res = requests.post(url, headers=headers, json=payload, verify=False).json()
        return res["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Ошибка запроса: {e}"

@app.route("/", methods=["GET"])
def index():
    return "Bot is alive!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json()
    if update and "message" in update and "text" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"]["text"]
        
        answer = ask_gigachat(text)
        
        send_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(send_url, json={"chat_id": chat_id, "text": answer})
        
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
