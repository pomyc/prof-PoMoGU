import os
import openai
from flask import jsonify

openai.api_key = os.getenv("OPENAI_API_KEY")

def handle_message(data):
    message = data['message']['text']
    chat_id = data['message']['chat']['id']
    reply = ask_gpt(message)
    return jsonify({"method": "sendMessage", "chat_id": chat_id, "text": reply})

def ask_gpt(message):
    try:
        if any(word in message.lower() for word in ["звільнення", "оплата", "вибори", "делегат", "відпустка"]):
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Ви профспілковий помічник. Відповідайте коротко, ввічливо, зрозуміло."},
                    {"role": "user", "content": message}
                ]
            )
            return response.choices[0].message.content
        else:
            return (
                "🔍 Не вдалося знайти точної відповіді.
"
                "📍 Зверніться до профспілки:
"
                "Дніпро, пр. Д.Яворницького, 93, к.327
"
                "📞 050 324-54-11
📧 profpmgu@gmail.com"
            )
    except Exception as e:
        return f"⚠️ Виникла помилка: {str(e)}"