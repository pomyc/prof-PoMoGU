import os
import openai
from flask import jsonify
from seniority_calculator import calculate_seniority
import chromadb
from chromadb.config import Settings

# Підключення OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Ініціалізація локальної бази знань ChromaDB
chroma_client = chromadb.Client(Settings(
    persist_directory="./knowledge_base",
    chroma_db_impl="duckdb+parquet"
))

collection = chroma_client.get_or_create_collection(name="prof_union_knowledge")

# Стани користувачів (для правильної обробки стажу чи бази знань)
user_state = {}

def handle_message(data):
    message = data['message']['text']
    chat_id = data['message']['chat']['id']
    user_id = data['message']['from']['id']

    # Якщо старт або початок роботи
    if message.strip().lower() in ["/start", "start"]:
        return jsonify({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "👋 Вітаю! Я профспілковий помічник. Оберіть дію:",
            "reply_markup": {
                "keyboard": [
                    [{"text": "📋 Задати питання"}],
                    [{"text": "📅 Розрахунок трудового стажу"}],
                    [{"text": "📚 Запит до профспілкової БД"}],
                    [{"text": "📞 Контакти профспілки"}]
                ],
                "resize_keyboard": True,
                "one_time_keyboard": False
            }
        })

    # Якщо користувач обирає "Розрахунок трудового стажу"
    if message.strip() == "📅 Розрахунок трудового стажу":
        user_state[user_id] = "awaiting_seniority_input"
        return jsonify({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "📅 Введіть дату початку та дату завершення роботи через крапку з комою (;).\nПриклад:\n01.09.2015; 24.04.2025\nАбо одну дату, якщо працюєте досі."
        })

    if user_state.get(user_id) == "awaiting_seniority_input":
        reply = calculate_seniority_input(message)
        user_state.pop(user_id, None)
        return jsonify({"method": "sendMessage", "chat_id": chat_id, "text": reply})

    # Якщо користувач обирає "Контакти профспілки"
    if message.strip() == "📞 Контакти профспілки":
        return jsonify({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "📍 Дніпро, пр. Д.Яворницького, 93, оф. 327\n📞 050 324-54-11\n📧 profpmgu@gmail.com\n🌐 http://pmguinfo.dp.ua"
        })

    # Якщо користувач обирає "Запит до профспілкової БД"
    if message.strip() == "📚 Запит до профспілкової БД":
        user_state[user_id] = "awaiting_knowledge_query"
        return jsonify({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "📚 Введіть Ваше питання для пошуку у базі знань:"
        })

    if user_state.get(user_id) == "awaiting_knowledge_query":
        reply = search_in_knowledge_base(message)
        user_state.pop(user_id, None)
        return jsonify({"method": "sendMessage", "chat_id": chat_id, "text": reply})

    # В іншому випадку — працює як "Задати питання" через GPT
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
            "⚠️ Невірний формат. Переконайтесь, що Ви ввели дати у форматі ДД.ММ.РРРР.\n"
            "Приклад: 01.09.2015; 24.04.2025"
        )

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
        print(f"❌ GPT error: {e}")
        return (
            "🔍 Не вдалося знайти точної відповіді.\n"
            "📍 Зверніться до профспілки:\n"
            "Дніпро, пр. Д.Яворницького, 93, к.327\n"
            "📞 050 324-54-11\n"
            "📧 profpmgu@gmail.com"
        )

def search_in_knowledge_base(query):
    try:
        results = collection.query(
            query_texts=[query],
            n_results=1
        )
        documents = results.get('documents', [[]])[0]

        if not documents:
            return "📚 Інформація відсутня у внутрішній базі знань."

        doc_text = documents[0]

        return (
            f"📚 Відповідь на основі бази знань:\n\n"
            f"{doc_text}\n\n"
            f"Джерело: внутрішня база профспілки"
        )
    except Exception as e:
        print(f"❌ Search error: {e}")
        return "⚠️ Сталася помилка при пошуку у базі знань."
