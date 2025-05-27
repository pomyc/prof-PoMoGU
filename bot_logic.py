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
    """Определяет, релевантен ли документ для запроса (упрощенная версия)"""
    content = result.page_content.lower()
    source = result.metadata.get('source', '').lower()
    query_lower = query.lower()
    
    # Проверяем, является ли это избирательным документом
    election_indicators = [
        'vybory' in source,
        'вибори' in source,
        'election' in source
    ]
    
    is_election_document = any(election_indicators)
    
    # Если это избирательный документ, проверяем контекст запроса
    if is_election_document:
        # Разрешаем избирательные документы только для избирательных вопросов
        election_query_terms = ['вибори', 'виборча', 'звітно-виборча', 'голосування', 'кандидат', 'делегат']
        is_election_query = any(term in query_lower for term in election_query_terms)
        
        if not is_election_query:
            print(f"🚫 БЛОКИРОВАН избирательный документ для неизбирательного запроса: {source}")
            return False
    
    return True

def calculate_relevance_score(result, query):
    """Улучшенная система оценки релевантности с правильными весами"""
    content = result.page_content.lower()
    source = result.metadata.get('source', '').lower()
    query_lower = query.lower()
    
    score = 0
    
    # Извлекаем слова из запроса (исключая короткие)
    query_words = [word for word in re.findall(r'\w+', query_lower) if len(word) > 2]
    
    # БАЗОВЫЕ совпадения слов (увеличили вес)
    word_matches = 0
    for word in query_words:
        if word in content:
            score += 8  # Увеличили с 5 до 8
            word_matches += 1
    
    # Специальная обработка для вопросов о взносах
    dues_keywords = ['внесок', 'внески', 'взнос', 'плата', 'розмір', 'сума', 'скільки', 'який']
    is_dues_query = any(keyword in query_lower for keyword in dues_keywords)
    
    if is_dues_query:
        print(f"💰 Обнаружен запрос о взносах: {query[:50]}")
        
        # Ключевые финансовые термины для взносов
        high_value_terms = ['внесок', 'внески', 'плата', 'розмір', 'сума']
        context_terms = ['грн', 'гривень', 'процент', '%', 'ставка', 'тариф', 'оплата', 'кошти', 'заробітн']
        
        financial_matches = 0
        
        # Высокий балл за прямые упоминания взносов
        for term in high_value_terms:
            if term in content:
                score += 30  # Уменьшили с 50 до 30
                financial_matches += 1
                print(f"💵 Найден финансовый термин '{term}' в {source}")
        
        # Средний балл за контекстные финансовые термины
        for term in context_terms:
            if term in content:
                score += 10  # Уменьшили с 15 до 10
                financial_matches += 1
        
        # Бонус за источник "статут" + финансовые термины
        if 'статут' in source and financial_matches > 0:
            score += 40  # Уменьшили с 100 до 40
            print(f"📋 Бонус за статут с финансовыми терминами: {source}")
        
        # Бонус за источник "galuzeva" (отраслевое соглашение)
        if 'galuzeva' in source and financial_matches > 0:
            score += 25
            print(f"🏭 Бонус за отраслевое соглашение: {source}")
        
        # Бонус за конкретные фразы о размере взносов
        specific_phrases = [
            'розмір внеск', 'сума внеск', 'розмір плат', 'сума плат',
            'скільки внеск', 'який внесок', 'процент від зарплат', 'відсоток від заробітн',
            'членський внесок', 'профспілковий внесок'
        ]
        for phrase in specific_phrases:
            if phrase in content:
                score += 35  # Уменьшили с 60 до 35
                print(f"🎯 Найдена специфическая фраза: '{phrase}'")
    else:
        # Для других типов вопросов - стандартная обработка
        # Бонус за профсоюзные термины
        union_terms = ['профспілка', 'профком', 'металург', 'гірник', 'член', 'організація']
        for term in union_terms:
            if term in query_lower and term in content:
                score += 12  # Увеличили с 10 до 12
    
    # Бонус за длинный контент (больше информации)
    if len(result.page_content) > 200:
        score += 5
    elif len(result.page_content) > 500:
        score += 10
    
    # Штраф за слишком короткий контент (менее 30 символов)
    if len(result.page_content) < 30:
        score -= 15
    
    # Уменьшили штраф за документы-заголовки
    title_indicators = ['затверджено', 'статут', 'визначення термінів', 'зміст', 'розділ']
    title_matches = sum(1 for indicator in title_indicators if indicator in content)
    if title_matches >= 3 and len(result.page_content) < 100:
        score -= 10  # Уменьшили с 20 до 10
    
    print(f"🔢 Файл: {source}, запрос: '{query[:30]}...', балл: {score}")
    return score

def search_in_knowledge_base(query):
    """Поиск в базе знаний с исправленной фильтрацией"""
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
            # Сначала проверяем базовую релевантность (блокировка нерелевантных документов)
            if not is_document_relevant(result, query):
                continue
                
            score = calculate_relevance_score(result, query)
            scored_results.append((result, score))
            
            if score >= 12:  # ПОНИЗИЛИ порог с 20 до 12
                print(f"✅ ПРИНЯТ документ: {result.metadata.get('source', 'unknown')}, балл: {score}")
            else:
                print(f"❌ ОТКЛОНЕН документ: {result.metadata.get('source', 'unknown')}, балл: {score}")
        
        # Фильтруем по минимальному порогу
        relevant_results = [(result, score) for result, score in scored_results if score >= 12]
        
        print(f"📊 Всего результатов: {len(results)}, после фильтрации: {len(relevant_results)}")
        
        # Если после фильтрации ничего не осталось, используем более мягкий порог
        if not relevant_results:
            print("⚠️ Применяем мягкий порог (балл >= 8)")
            relevant_results = [(result, score) for result, score in scored_results if score >= 8]
            
            if not relevant_results:
                print("⚠️ Применяем очень мягкий порог (балл >= 5)")
                relevant_results = [(result, score) for result, score in scored_results if score >= 5]
        
        if not relevant_results:
            return "📚 У базі знань не знайдено релевантної інформації на це питання. Зверніться до профспілки за детальною консультацією:\n📞 050 324-54-11\n📧 profpmgu@gmail.com"
        
        # Сортируем по релевантности и берем только топ-3
        relevant_results.sort(key=lambda x: x[1], reverse=True)
        top_results = relevant_results[:3]
        
        # Формируем ответ
        response = "📖 Знайдена релевантна інформація:\n\n"
        
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
    """GPT с исправленным контекстом"""
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
                        # Проверяем базовую релевантность
                        if not is_document_relevant(result, message):
                            continue
                            
                        score = calculate_relevance_score(result, message)
                        scored_results.append((result, score))
                    
                    # ПОНИЗИЛИ порог релевантности для GPT контекста
                    min_score = 15  # Понизили с 25 до 15
                    relevant_results = []
                    for result, score in scored_results:
                        if score >= min_score:
                            relevant_results.append((result, score))
                    
                    # Если ничего не найдено, применяем еще более мягкий порог
                    if not relevant_results:
                        min_score = 10
                        relevant_results = [(result, score) for result, score in scored_results if score >= min_score]
                        print(f"⚠️ Применяем мягкий порог для GPT контекста: {min_score}")
                    
                    if relevant_results:
                        # Берем только топ-2 самых релевантных
                        relevant_results.sort(key=lambda x: x[1], reverse=True)
                        top_relevant = relevant_results[:2]
                        
                        context = "\n\nРелевантна інформація з бази знань:\n"
                        for result, score in top_relevant:
                            source = result.metadata.get('source', 'документ')
                            content = result.page_content[:300]
                            context += f"З {source} (релевантність: {score}): {content}...\n\n"
                        
                        print(f"✅ Найдено {len(top_relevant)} релевантных документов для GPT контекста")
                    else:
                        print(f"⚠️ Не знайдено релевантного контексту (мінімальний бал {min_score})")
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
