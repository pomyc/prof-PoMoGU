import os
import openai
from flask import jsonify
from seniority_calculator import calculate_seniority
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

# API ключ OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Ініціалізація FAISS векторної бази
try:
    embeddings = OpenAIEmbeddings(openai_api_key=os.getenv("OPENAI_API_KEY"))
    vectorstore = FAISS.load_local(
        "./knowledge_base", 
        embeddings,
        allow_dangerous_deserialization=True
    )
    print("📦 Векторна база FAISS успішно завантажена")
except Exception as e:
    print(f"❌ Помилка завантаження векторної бази: {e}")
    vectorstore = None

# Стан користувачів
user_state = {}

# Основна функція
def handle_message(data):
    message_obj = data.get("message", {})
    message = message_obj.get("text")
    chat_id = message_obj.get("chat", {}).get("id")
    user_id = message_obj.get("from", {}).get("id")

    if not message or not chat_id:
        return jsonify({
            "method": "sendMessage",
            "chat_id": chat_id or 0,
            "text": "⚠️ Я розумію тільки текстові повідомлення."
        })

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
            "text": "📅 Введіть дату початку та завершення роботи через крапку з комою (;)\nНаприклад:\n01.09.2015; 24.04.2025\nабо тільки одну дату, якщо досі працюєте."
        })

    if user_state.get(user_id) == "awaiting_seniority_input":
        reply = calculate_seniority_input(message)
        user_state.pop(user_id, None)
        return jsonify({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": reply
        })

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
        return jsonify({
            "method": "sendMessage",
            "chat_id": chat_id,
            "text": reply
        })

    # GPT — основна відповідь
    reply = ask_gpt(message)
    return jsonify({
        "method": "sendMessage",
        "chat_id": chat_id,
        "text": reply
    })

# Розрахунок стажу
def calculate_seniority_input(message):
    try:
        if ";" in message:
            start_date, end_date = [d.strip() for d in message.split(";")]
            return calculate_seniority(start_date, end_date)
        else:
            return calculate_seniority(message.strip())
    except Exception:
        return "⚠️ Невірний формат. Напишіть, наприклад:\n01.09.2015; 24.04.2025"

# GPT-відповідь з використанням контексту з бази знань
def ask_gpt(message):
    try:
        # Спробуємо знайти релевантну інформацію в базі знань
        context = ""
        if vectorstore:
            try:
                results = vectorstore.similarity_search(message, k=2)
                if results:
                    context = "\n\nДодаткова інформація з бази знань:\n"
                    for result in results:
                        context += f"- {result.page_content[:300]}...\n"
            except Exception as e:
                print(f"⚠️ Помилка пошуку в базі знань: {e}")

        system_message = (
            "Ти профспілковий помічник. Відповідай офіційною українською мовою, посилаючись на статті КЗпП, якщо це можливо. "
            "Наприклад: 'Відповідно до ст. 21 КЗпП України...' Якщо не знаєш відповіді, напиши, що потрібно звернутися за консультацією до юриста профспілки. "
            "Якщо питання стосується трудових прав, соціальних гарантій або профспілкового захисту — дай конкретну відповідь та посилання на норми законодавства."
        )

        user_message = message + context

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            temperature=0.3,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
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

# Пошук у локальній базі знань з FAISS
def search_in_knowledge_base(query):
    try:
        if not vectorstore:
            return "⚠️ База знань недоступна. Спробуйте пізніше."
        
        print(f"🔍 Пошук у базі знань: {query}")
        
        # Пошук найбільш релевантних документів
        results = vectorstore.similarity_search(query, k=3)
        
        if not results:
            return "📚 У базі знань не знайдено відповіді на це питання."
        
        # Формуємо відповідь з найкращих результатів
        response = "📖 Знайдено в базі знань:\n\n"
        
        for i, result in enumerate(results, 1):
            source = result.metadata.get('source', 'Невідоме джерело')
            content = result.page_content.strip()
            
            response += f"📄 Джерело: {source}\n"
            response += f"{content}\n"
            
            if i < len(results):
                response += "\n" + "="*30 + "\n\n"
        
        return response
        
    except Exception as e:
        print(f"❌ DB error: {e}")
        return "⚠️ Сталася помилка при пошуку в базі знань."

# Функція для RAG (Retrieval-Augmented Generation) - покращена відповідь GPT з контекстом
def ask_gpt_with_context(message, use_knowledge_base=True):
    """
    Покращена функція для отримання відповіді від GPT з використанням контексту з бази знань
    """
    try:
        context = ""
        
        if use_knowledge_base and vectorstore:
            try:
                # Знаходимо релевантну інформацію в базі знань
                results = vectorstore.similarity_search(message, k=3)
                if results:
                    context = "\n\nКонтекст з бази знань профспілки:\n"
                    for result in results:
                        source = result.metadata.get('source', 'документ')
                        context += f"З {source}: {result.page_content[:400]}...\n\n"
            except Exception as e:
                print(f"⚠️ Помилка пошуку контексту: {e}")

        system_message = (
            "Ти експерт з трудового права та профспілкового захисту в Україні. "
            "Відповідай професійно українською мовою, використовуючи наданий контекст та посилаючись на статті КЗпП України, якщо це доречно. "
            "Якщо питання виходить за межі твоїх знань, рекомендуй звернутися до юриста профспілки. "
            "Структуруй відповідь чітко та логічно."
        )

        user_message = f"Питання: {message}"
        if context:
            user_message += f"\n\n{context}"

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            temperature=0.2,
            max_tokens=1000,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
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
