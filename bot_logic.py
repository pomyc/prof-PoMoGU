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

# Основная функция
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

def is_document_relevant(result, query):
    """Определяет, релевантен ли документ для запроса"""
    content = result.page_content.lower()
    source = result.metadata.get('source', '').lower()
    query_lower = query.lower()
    
    # ЖЕСТКАЯ БЛОКИРОВКА избирательных документов для финансовых вопросов
    dues_keywords = ['внесок', 'внески', 'взнос', 'плата', 'розмір', 'сума', 'скільки', 'який розмір']
    is_dues_query = any(keyword in query_lower for keyword in dues_keywords)
    
    # Проверяем, является ли это избирательным документом
    election_indicators = [
        'vybory' in source,
        'вибори' in source,
        'виборча' in content,
        'звітно-виборча' in content,
        'голосування' in content,
        'кандидат' in content
    ]
    
    is_election_document = any(election_indicators)
    
    # Если это вопрос о взносах и документ избирательный - БЛОКИРУЕМ
    if is_dues_query and is_election_document:
        print(f"🚫 БЛОКИРОВАН избирательный документ для вопроса о взносах: {source}")
        return False
    
    # Для избирательных документов в других случаях - тоже блокируем
    if is_election_document and not any(term in query_lower for term in ['вибори', 'виборча', 'звітно-виборча']):
        print(f"🚫 БЛОКИРОВАН избирательный документ: {source}")
        return False
    
    return True

def calculate_relevance_score(result, query):
    """Улучшенная система оценки релевантности"""
    content = result.page_content.lower()
    source = result.metadata.get('source', '').lower()
    query_lower = query.lower()
    
    # Сначала проверяем базовую релевантность
    if not is_document_relevant(result, query):
        return -1000  # Огромный отрицательный балл для заблокированных документов
    
    score = 0
    
    # Извлекаем слова из запроса (исключая короткие)
    query_words = [word for word in re.findall(r'\w+', query_lower) if len(word) > 2]
    
    # Базовые совпадения слов
    for word in query_words:
        if word in content:
            score += 5
    
    # Специальная обработка для вопросов о взносах
    dues_keywords = ['внесок', 'внески', 'взнос', 'плата', 'розмір', 'сума', 'скільки', 'який розмір']
    financial_terms = ['внесок', 'внески', 'плата', 'сума', 'розмір', 'грн', 'гривень', 'процент', '%', 'ставка', 'тариф', 'оплата', 'кошти']
    
    is_dues_query = any(keyword in query_lower for keyword in dues_keywords)
    has_financial_content = any(term in content for term in financial_terms)
    
    if is_dues_query and has_financial_content:
        score += 100  # Увеличили бонус за финансовый контент
        
        # Дополнительный бонус за источник "статут"
        if 'статут' in source:
            score += 50
    
    # Бонус за профсоюзные термины
    union_terms = ['профспілка', 'профком', 'металург', 'гірник', 'член', 'організація']
    for term in union_terms:
        if term in query_lower and term in content:
            score += 3
    
    print(f"🔢 Файл: {source}, запрос: '{query[:30]}...', балл: {score}")
    return score

def search_in_knowledge_base(query):
    """Поиск в базе знаний с улучшенной фильтрацией"""
    try:
        if not vectorstore:
            return "⚠️ База знань недоступна. Спробуйте пізніше."
        
        print(f"🔍 Пошук у базі знань: {query}")
        
        # Выполняем векторный поиск
        results = vectorstore.similarity_search(query, k=15)
        
        if not results:
            return "📚 У базі знань не знайдено відповіді на це питання."
        
        # Оцениваем релевантность каждого результата
        scored_results = []
        for result in results:
            score = calculate_relevance_score(result, query)
            scored_results.append((result, score))
        
        # Сортируем по релевантности
        scored_results.sort(key=lambda x: x[1], reverse=True)
        
        # СТРОГАЯ фильтрация: только результаты с положительным баллом
        good_results = [(result, score) for result, score in scored_results if score > 0]
        
        print(f"📊 Всего результатов: {len(results)}, с положительным баллом: {len(good_results)}")
        
        if not good_results:
            return "📚 У базі знань не знайдено релевантної інформації на це питання."
        
        # Берем только топ-3 результата
        top_results = good_results[:3]
        
        # Формируем ответ
        response = "📖 Знайдена інформація з бази знань:\n\n"
        
        for i, (result, score) in enumerate(top_results, 1):
            source = result.metadata.get('source', 'Невідоме джерело')
            content = result.page_content.strip()
            
            # Ограничиваем длину контента
            if len(content) > 400:
                content = content[:400] + "..."
            
            response += f"📄 Джерело: {source} (релевантність: {score})\n"
            response += f"{content}\n"
            
            if i < len(top_results):
                response += "\n" + "="*30 + "\n\n"
        
        return response
        
    except Exception as e:
        print(f"❌ DB error: {e}")
        return "⚠️ Сталася помилка при пошуку в базі знань."

def ask_gpt_with_smart_context(message):
    """GPT с улучшенным контекстом"""
    try:
        context = ""
        
        if vectorstore:
            try:
                # Выполняем семантический поиск
                results = vectorstore.similarity_search(message, k=10)
                
                if results:
                    # Оцениваем релевантность
                    scored_results = []
                    for result in results:
                        score = calculate_relevance_score(result, message)
                        scored_results.append((result, score))
                    
                    # СТРОГИЙ порог релевантности
                    min_score = 25  # Увеличили порог
                    relevant_results = [(result, score) for result, score in scored_results if score >= min_score]
                    
                    if relevant_results:
                        # Берем только топ-2 самых релевантных
                        relevant_results.sort(key=lambda x: x[1], reverse=True)
                        top_relevant = relevant_results[:2]
                        
                        context = "\n\nРелевантна інформація з бази знань:\n"
                        for result, score in top_relevant:
                            source = result.metadata.get('source', 'документ')
                            content = result.page_content[:300]
                            context += f"З {source} (релевантність: {score}): {content}...\n\n"
                    else:
                        print("⚠️ Не знайдено релевантного контексту (мінімальний бал 25)")
            except Exception as e:
                print(f"⚠️ Помилка пошуку контексту: {e}")

        system_message = (
            "Ти професійний помічник з питань профспілкової діяльності та трудового права України. "
            "Відповідай українською мовою, професійно та точно. "
            "Якщо в наданому контексті є точна відповідь на питання - використовуй її. "
            "Якщо контекст не містить відповіді або не релевантний - чесно скажи про це "
            "і дай загальну інформацію на основі знань про трудове право України. "
            "При необхідності посилайся на статті КЗпП України. "
            "Якщо не знаєш точної відповіді - краще направ до профспілки за консультацією."
        )

        user_message = f"Питання: {message}"
        if context:
            user_message += f"\n{context}"
        else:
            user_message += "\n\nПримітка: релевантної інформації в базі знань не знайдено."

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
