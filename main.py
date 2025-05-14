import os
import sys
import logging
import requests
import zipfile
from flask import Flask, request
from bot_logic import handle_message

# 📦 Автоматичне завантаження та розпакування бази знань
def download_and_extract_kb():
    kb_dir = "./knowledge_base"
    zip_path = "knowledge_base.zip"
    url = "https://www.dropbox.com/scl/fi/9fudqmgmqdzk70fqgo8nw/knowledge_base.zip?rlkey=ft9yyx596if4twx2yg44omq34&st=uwz3607e&dl=1"

    if not os.path.exists(kb_dir):
        print("📦 Завантажую базу знань з Dropbox...")
        r = requests.get(url)
        with open(zip_path, "wb") as f:
            f.write(r.content)

        print("🗂️ Розпаковую архів...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(".")
        print("✅ База знань готова!")

# Виклик перед запуском Flask
download_and_extract_kb()

# Flask
logging.basicConfig(stream=sys.stdout, level=logging.INFO)
app = Flask(__name__)

@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    return handle_message(data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
