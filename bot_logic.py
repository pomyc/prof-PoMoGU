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
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ви профспілковий помічник. Відповідайте коротко, ввічливо, зрозуміло."},
                {"role": "user", "content": message}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return (
            "🔍 Не вдалося знайти точної відповіді.\n"
            "📍 Зверніться до профспілки:\n"
            "Дніпро, пр. Д.Яворницького, 93, к.327\n"
            "📞 050 324-54-11\n"
            "📧 profpmgu@gmail.com"
        )
    except Exception as e:
        return f"⚠️ Виникла помилка: {str(e)}"
