import os
import openai
from flask import jsonify
from seniority_calculator import calculate_seniority

openai.api_key = os.getenv("OPENAI_API_KEY")

# Простий user_state — словник для зберігання "режиму"
user_state = {}

def handle_message(data):
    message = data['message']['text']
    chat_id = data['message']['chat']['id']
    user_id = data['message']['from']['id']

    # Якщо користувач у режимі розрахунку стажу
    if user_state.get(user_id) == "awaiting_seniority_input":
        reply = calculate_seniority_input(message)
        user_state.pop(user_id, None)  # Очистити стан
        return jsonify({"method": "sendMessage", "chat_id": chat_id, "text": reply})

    # Якщо команда /стаж або натискання кнопки
    if message.strip().lower() in ["/стаж", "розрахунок трудового стажу"]:
        user_state[user_id] = "awaiting_seniority_input"
        return jsonify({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "📅 Введіть дату початку та дату завершення роботи через крапку з комами.\nНаприклад:\n01.09.2015; 24.04.2025\nАбо просто одну дату, якщо працюєте досі."
        })

    # Основна GPT-логіка
    reply = ask_gpt(message)
    return jsonify({"method": "sendMessage", "chat_id": chat_id, "text": reply})

def calculate_seniority_input(message):
    try:
        if ";" in message:
            start_date, end_date = [d.strip() for d in message.split(";")]
            return calculate_seniority(start_date, end_date)
        else:
            return calculate_seniority(message.strip())
    except Exception as e:
        return (
            "⚠️ Невірний формат. Переконайтесь, що ви ввели дати у форматі ДД.ММ.РРРР\n"
            "Наприклад: 01.09.2015; 24.04.2025"
        )

def ask_gpt(message):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ви профспілковий помічник. Відповідайте коротко, ввічливо, зрозуміло."},
                {"role": "user", "content": message}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ GPT error: {e}")
        return (
            "🔍 Не вдалося знайти точної відповіді.\n"
            "📍 Зверніться до профспілки:\n"
            "Дніпро, пр. Д.Яворницького, 93, к.327\n"
            "📞 050 324-54-11\n"
            "📧 profpmgu@gmail.com"
        )
