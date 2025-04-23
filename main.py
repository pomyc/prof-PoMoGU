from flask import Flask, request
from bot_logic import handle_message

app = Flask(__name__)

@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    return handle_message(data)