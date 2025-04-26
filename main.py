from flask import Flask, request
from bot_logic import handle_message
from seniority_calculator import calculate_seniority
import os
import sys
import logging

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

app = Flask(__name__)

# Простий обробник для запиту розрахунку стажу
@app.route("/seniority", methods=["POST"])
def seniority():
    data = request.get_json()
    chat_id = data['message']['chat']['id']
    text = data['message']['text'].strip()

    try:
        if ";" in text:
            _, dates = text.split(" ", 1)
            start_date, end_date = [d.strip() for d in dates.split(";")]
            reply = calculate_seniority(start_date, end_date)
        else:
            _, start_date = text.split(" ", 1)
            reply = calculate_seniority(start_date.strip())

        return {
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": reply
        }
    except Exception as e:
        return {
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "⚠️ Невірний формат. Напишіть, наприклад:
`/стаж 01.09.2015; 24.04.2025`"
        }

@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    return handle_message(data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
