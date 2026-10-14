import os
import csv
import io
import requests
import urllib3
from flask import Flask, request, render_template, Response

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

GIGACHAT_AUTH_KEY = os.environ.get("GIGACHAT_AUTH_KEY")
SPREADSHEET_ID = "115oOjWSwkFUuZnBomimcbvPsf_c6cyqmbgrFwyFSVE"

SHEET_GIDS = {
    "all": ["0", "1433962862", "1202844813"],
    "sheet1": ["0", "1433962862"],
    "goods": ["1202844813"]
}

def get_gigachat_token():
    print("=== НАЧАЛО ЗАПРОСА ТОКЕНА GIGACHAT ===")
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    payload = {'scope': 'GIGACHAT_API_PERS'}
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'RQUID': '6f002237-3318-48b6-86716d006324',
        'Authorization': f'Basic {GIGACHAT_AUTH_KEY}'
    }
    print(f"URL: {url}")
    print(f"Auth Key length: {len(GIGACHAT_AUTH_KEY) if GIGACHAT_AUTH_KEY else 'КЛЮЧ ОТСУТСТВУЕТ!'}")
    
    try:
        response = requests.post(url, headers=headers, data=payload, verify=False, timeout=15)
        print(f"Token status code: {response.status_code}")
        print(f"Token response text: {response.text}")
        if response.status_code == 200:
            return response.json().get('access_token')
    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА запроса токена: {e}")
    print("=== КОНЕЦ ЗАПРОСА ТОКЕНА ===")
    return None
