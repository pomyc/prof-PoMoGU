import os
import openai
from flask import jsonify
from seniority_calculator import calculate_seniority
import chromadb
from chromadb.config import Settings

openai.api_key = os.getenv("OPENAI_API_KEY")

# Ініціалізація локальної бази знань ChromaDB
chroma_client = chromadb.Client(Settings(
    persist_directory="./knowledge_base",
    chroma_db_impl="duckdb+parquet"
))

collection = chroma_client.get_or_create_collection(name="prof_union_knowledge")
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
                    [{"text": "📚 Запит до бази знань"}],
                    [{"text": "📅 Розрахунок трудового стажу"}],
                    [{"text": "📞 Контакти профспілки"}]
                ],
                "resize_keyboard": True
            }
        })
        
  # Якщо користувач обирає "Контакти профспілки"
    if message == "📞 Контакти профспілки":
        return jsonify({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "📍 Дніпро, пр. Д.Яворницького, 93, оф. 327\n📞 050 324-54-11\n📧 profpmgu@gmail.com\n🌐 http://pmguinfo.dp.ua"
        })
        
  # Якщо користувач обирає "Запит до бази знань"
    if message == "📚 Запит до бази знань":
        user_state[user_id] = "awaiting_knowledge_query"
        return jsonify({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": "📚 Введіть запит, і я спробую знайти відповідь у базі знань:"
        })

if user_state.get(user_id) == "awaiting_knowledge_query":
    reply = search_in_knowledge_base(message)
    user_state.pop(user_id, None)
    return jsonify({"method": "sendMessage", "chat_id": chat_id, "text": reply})
    
    # Якщо користувач обирає "Розрахунок трудового стажу"
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
    return jsonify({"method": "sendMessage", "chat_id": chat_id, "text": reply})

def search_in_knowledge_base(query):
    try:
        results = collection.query(query_texts=[query], n_results=1)
        documents = results.get('documents', [[]])[0]
        if not documents:
            return "📚 У базі знань немає відповіді на це питання."
        return f"📖 Знайдено в базі:\n\n{documents[0]}"
    except Exception as e:
        print(f"❌ DB error: {e}")
        return "⚠️ Помилка при зверненні до бази знань."

def calculate_seniority_input(message):
    try:
        if ";" in message:
            start_date, end_date = [d.strip() for d in message.split(";")]
            return calculate_seniority(start_date, end_date)
        else:
            return calculate_seniority(message.strip())
    except Exception:
        return "⚠️ Невірний формат. Приклад: 01.09.2015; 24.04.2025"


def ask_gpt(message):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            temperature=0.3,
            messages=[
                {
                    "role": "system",
                    "content": (
"Ти профспілковий помічник. Відповідай офіційною українською мовою, посилаючись на статті КЗпП, якщо це можливо. Наприклад: 'Відповідно до ст. 21 КЗпП України...' Якщо не знаєш відповіді, напиши, що потрібно звернутися за консультацією до юриста профспілки. "
                "Якщо питання стосується трудових прав, соціальних гарантій або профспілкового захисту — дай конкретну відповідь та посилання на норми законодавства. "
                    )
                },
                {"role": "user", "content": message}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ GPT error: {e}")
        return (
            "🔍 Не вдалося отримати відповідь.\n"
            "📍 Зверніться до профспілки:\n"
            "Дніпро, пр. Д.Яворницького, 93, к.327\n"
            "📞 050 324-54-11\n"
            "📧 profpmgu@gmail.com"
        )
