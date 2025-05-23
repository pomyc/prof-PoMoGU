import os
import sys
import logging
import requests
import zipfile
from flask import Flask, request

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
