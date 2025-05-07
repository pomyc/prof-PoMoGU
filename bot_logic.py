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

    if message.strip().lower() in ["/start", "start"]:
        return jsonify({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "👋 Вітаю! Я профспілковий помічник. Оберіть дію:",
            "reply_markup": {
                "keyboard": [
                    [{"text": "📋 Задати питання"}],
                    [{"text": "📅 Розрахунок трудового стажу"}],
                    [{"text": "📞 Контакти профспілки"}]
                ],
                "resize_keyboard": True
            }
        })

    if message == "📞 Контакти профспілки":
        return jsonify({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "📍 Дніпро, пр. Д.Яворницького, 93, оф. 327\n📞 050 324-54-11\n📧 profpmgu@gmail.com\n🌐 http://pmguinfo.dp.ua"
        })

    if message == "📅 Розрахунок трудового стажу":
        user_state[user_id] = "awaiting_seniority_input"
        return jsonify({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "📅 Введіть дату початку та завершення роботи через крапку з комою (;)\nПриклад:\n01.09.2015; 24.04.2025\nабо тільки одну дату, якщо досі працюєте."
        })

    if user_state.get(user_id) == "awaiting_seniority_input":
        reply = calculate_seniority_input(message)
        user_state.pop(user_id, None)
        return jsonify({"method": "sendMessage", "chat_id": chat_id, "text": reply})

    # GPT-відповідь (останнім, якщо нічого не збіглося)
    reply = ask_gpt(message)
    return jsonify({"method": "sendMessage", "chat_id": chat_id, "text": reply})def handle_message(data):
    message = data['message']['text']
    chat_id = data['message']['chat']['id']
    user_id = data['message']['from']['id']

    if message.strip().lower() in ["/start", "start"]:
        return jsonify({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "👋 Вітаю! Я профспілковий помічник. Оберіть дію:",
            "reply_markup": {
                "keyboard": [
                    [{"text": "📋 Задати питання"}],
                    [{"text": "📅 Розрахунок трудового стажу"}],
                    [{"text": "📞 Контакти профспілки"}]
                ],
                "resize_keyboard": True
            }
        })

    if message == "📞 Контакти профспілки":
        return jsonify({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "📍 Дніпро, пр. Д.Яворницького, 93, оф. 327\n📞 050 324-54-11\n📧 profpmgu@gmail.com\n🌐 http://pmguinfo.dp.ua"
        })

    if message == "📅 Розрахунок трудового стажу":
        user_state[user_id] = "awaiting_seniority_input"
        return jsonify({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "📅 Введіть дату початку та завершення роботи через крапку з комою (;)\nПриклад:\n01.09.2015; 24.04.2025\nабо тільки одну дату, якщо досі працюєте."
        })

    if user_state.get(user_id) == "awaiting_seniority_input":
        reply = calculate_seniority_input(message)
        user_state.pop(user_id, None)
        return jsonify({"method": "sendMessage", "chat_id": chat_id, "text": reply})

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
            temperature=0.4,
            messages=[
        {
            "role": "system",
            "content": (
                "Ти профспілковий помічник. Відповідай офіційною українською мовою, посилаючись на статті КЗпП, якщо це можливо. Наприклад: 'Відповідно до ст. 21 КЗпП України...' Якщо не знаєш відповіді, напиши, що потрібно звернутися за консультацією до юриста профспілки. "
                "Якщо питання стосується трудових прав, соціальних гарантій або профспілкового захисту — дай конкретну пораду та посилання на норми законодавства. "
            )
        },
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
