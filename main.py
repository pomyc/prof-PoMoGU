import os
import sys
import logging
import requests
import zipfile
from flask import Flask, request

# 📦 Завантаження бази знань
def download_and_extract_kb():
    kb_dir = "./knowledge_base"
    zip_path = "knowledge_base.zip"
    url = "https://www.dropbox.com/scl/fi/nci5cvxjdifaw4kdb62ox/knowledge_base.zip?rlkey=xbx8ts6snx8c86br4mf8iw9if&st=dcrx64a1&dl=1"

    # 🔥 Видаляємо стару базу, якщо є
    if os.path.exists(kb_dir):
        import shutil
        shutil.rmtree(kb_dir)
        
    if not os.path.exists(os.path.join(kb_dir, "chroma.sqlite3")):
        print("📦 Завантажую базу знань з Dropbox...")
        r = requests.get(url)
        with open(zip_path, "wb") as f:
            f.write(r.content)

        print("🗂️ Розпаковую архів...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(".")
        print("✅ База знань готова!")

# 🛠️ Спочатку завантаж базу:
download_and_extract_kb()

# ✅ Лише після цього імпортуй логіку бота:
from bot_logic import handle_message, collection

print("🧠 Всього документів у базі:", collection.count())

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
