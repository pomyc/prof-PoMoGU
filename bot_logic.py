import os
import re
from flask import jsonify
from seniority_calculator import calculate_seniority
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv
from openai import OpenAI
from collections import Counter

# API ключ OpenAI
openai_api_key = os.getenv('OPENAI_API_KEY')
client = OpenAI(api_key=openai_api_key)

if not openai_api_key:
    print("❌ OpenAI API key not found!")
else:
    print(f"✅ OpenAI API key loaded: {openai_api_key[:10]}...")

# Ініціалізація FAISS векторної бази
try:
    embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)
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
    reply = ask_gpt_with_smart_context(message)
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
def preprocess_query(query):
    """Предобработка запроса для улучшения поиска"""
    # Приводим к нижнему регистру
    query = query.lower()
    
    # Удаляем лишние пробелы и знаки препинания
    query = re.sub(r'[^\w\s]', ' ', query)
    query = re.sub(r'\s+', ' ', query).strip()
    
    # Извлекаем ключевые слова
    keywords = query.split()
    
    # Словарь синонимов для улучшения поиска
    synonyms = {
        'внески': ['внесок', 'плата', 'взнос', 'оплата', 'кошти'],
        'розмір': ['сума', 'величина', 'розмір', 'кількість'],
        'профспілкові': ['профспілка', 'профком', 'організація'],
        'зарплата': ['заробітна плата', 'оплата праці', 'винагорода'],
        'відпустка': ['відпочинок', 'канікули', 'вихідні'],
        'звільнення': ['розірвання', 'припинення', 'закінчення']
    }
    
    # Расширяем запрос синонимами
    expanded_keywords = keywords.copy()
    for keyword in keywords:
        for base_word, synonym_list in synonyms.items():
            if keyword in synonym_list or keyword == base_word:
                expanded_keywords.extend(synonym_list)
    
    return ' '.join(list(set(expanded_keywords)))

def calculate_relevance_score(result, query_keywords):
    """Вычисляет релевантность результата"""
    content = result.page_content.lower()
    query_words = query_keywords.lower().split()
    
    score = 0
    content_words = re.findall(r'\w+', content)
    content_counter = Counter(content_words)
    
    for word in query_words:
        if len(word) > 2:  # Игнорируем слишком короткие слова
            # Точное совпадение
            if word in content_words:
                score += 10
            
            # Частичное совпадение
            for content_word in content_words:
                if word in content_word or content_word in word:
                    score += 5
    
    # Бонус за источник
    source = result.metadata.get('source', '').lower()
    if any(keyword in source for keyword in ['внесок', 'платіж', 'сума', 'розмір']):
        score += 15
    
    return score

def search_in_knowledge_base(query):
    """Улучшенный поиск в базе знаний"""
    try:
        if not vectorstore:
            return "⚠️ База знань недоступна. Спробуйте пізніше."
        
        print(f"🔍 Пошук у базі знань: {query}")
        
        # Предобработка запроса
        processed_query = preprocess_query(query)
        print(f"🔄 Обработанный запрос: {processed_query}")
        
        # Увеличиваем количество результатов для лучшей фильтрации
        results = vectorstore.similarity_search(processed_query, k=10)
        
        if not results:
            # Пробуем поиск по оригинальному запросу
            results = vectorstore.similarity_search(query, k=10)
        
        if not results:
            return "📚 У базі знань не знайдено відповіді на це питання."
        
        # Вычисляем релевантность и сортируем
        scored_results = []
        for result in results:
            score = calculate_relevance_score(result, query + ' ' + processed_query)
            scored_results.append((result, score))
        
        # Сортируем по релевантности
        scored_results.sort(key=lambda x: x[1], reverse=True)
        
        # Берем только самые релевантные (с минимальным порогом)
        relevant_results = [result for result, score in scored_results if score > 5][:3]
        
        if not relevant_results:
            return "📚 Не знайдено релевантної інформації в базі знань. Спробуйте перефразувати питання."
        
        # Формируем ответ
        response = "📖 Найкраща відповідь з бази знань:\n\n"
        
        for i, result in enumerate(relevant_results, 1):
            source = result.metadata.get('source', 'Невідоме джерело')
            content = result.page_content.strip()
            
            # Ограничиваем длину контента
            if len(content) > 500:
                content = content[:500] + "..."
            
            response += f"📄 Джерело: {source}\n"
            response += f"{content}\n"
            
            if i < len(relevant_results):
                response += "\n" + "="*30 + "\n\n"
        
        return response
        
    except Exception as e:
        print(f"❌ DB error: {e}")
        return "⚠️ Сталася помилка при пошуку в базі знань."

def ask_gpt_with_smart_context(message):
    """GPT с умным контекстом из базы знаний"""
    try:
        context = ""
        
        if vectorstore:
            try:
                # Используем улучшенный поиск
                processed_query = preprocess_query(message)
                results = vectorstore.similarity_search(processed_query, k=5)
                
                if results:
                    # Оцениваем релевантность
                    scored_results = []
                    for result in results:
                        score = calculate_relevance_score(result, message + ' ' + processed_query)
                        scored_results.append((result, score))
                    
                    # Берем только релевантные результаты
                    relevant_results = [result for result, score in scored_results if score > 10][:2]
                    
                    if relevant_results:
                        context = "\n\nРелевантна інформація з бази знань:\n"
                        for result in relevant_results:
                            source = result.metadata.get('source', 'документ')
                            content = result.page_content[:400]
                            context += f"З {source}: {content}...\n\n"
            except Exception as e:
                print(f"⚠️ Помилка пошуку контексту: {e}")

        system_message = (
            "Ти профспілковий помічник-експерт з трудового права України. "
            "Відповідай професійно українською мовою, використовуючи наданий контекст. "
            "Якщо в контексті є точна інформація - використовуй її. "
            "Якщо контекст не релевантний - відповідай на основі загальних знань про трудове право. "
            "Посилайся на статті КЗпП України, якщо це доречно. "
            "Структуруй відповідь чітко та логічно."
        )

        user_message = f"Питання: {message}"
        if context:
            user_message += f"\n{context}"

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            max_tokens=1000,
            temperature=0.3
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
