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

def extract_key_concepts(query):
    """Извлекает ключевые концепции из запроса"""
    query_lower = query.lower()
    
    concepts = {
        'взносы': ['внесок', 'внески', 'взнос', 'плата', 'платіж', 'оплата', 'кошти', 'сума', 'розмір'],
        'выборы': ['вибори', 'виборча', 'звітно-виборча', 'кампанія', 'голосування'],
        'отпуск': ['відпустка', 'відпочинок', 'канікули'],
        'увольнение': ['звільнення', 'розірвання', 'припинення'],
        'зарплата': ['зарплата', 'заробітна плата', 'оплата праці', 'винагорода'],
        'работа': ['робота', 'праця', 'трудовий', 'службовий'],
        'профсоюз': ['профспілка', 'профком', 'організація']
    }
    
    found_concepts = []
    for concept, keywords in concepts.items():
        if any(keyword in query_lower for keyword in keywords):
            found_concepts.append(concept)
    
    return found_concepts

def calculate_semantic_relevance(result, query, query_concepts):
    """Вычисляет семантическую релевантность результата"""
    content = result.page_content.lower()
    source = result.metadata.get('source', '').lower()
    
    score = 0
    
    # Проверяем соответствие основных концепций
    content_concepts = extract_key_concepts(content)
    
    # Высокий балл за совпадение ключевых концепций
    common_concepts = set(query_concepts) & set(content_concepts)
    score += len(common_concepts) * 50
    
    # Специальная проверка для вопросов о взносах
    if 'взносы' in query_concepts:
        money_keywords = ['грн', 'гривень', 'копійок', 'процент', '%', 'розмір', 'сума', 'ставка', 'тариф']
        if any(keyword in content for keyword in money_keywords):
            score += 100
        
        # Штраф за документы о выборах при вопросе о взносах
        if 'выборы' in content_concepts and 'взносы' not in content_concepts:
            score -= 200
    
    # Проверяем релевантность источника
    if 'взносы' in query_concepts:
        if any(word in source for word in ['внесок', 'плата', 'фінанс', 'бюджет']):
            score += 30
        if any(word in source for word in ['вибор', 'звіт']):
            score -= 50
    
    # Точные текстовые совпадения (с меньшим весом)
    query_words = set(re.findall(r'\w+', query.lower()))
    content_words = set(re.findall(r'\w+', content))
    
    exact_matches = query_words & content_words
    score += len(exact_matches) * 5
    
    return score

def search_in_knowledge_base(query):
    """Улучшенный семантический поиск в базе знаний"""
    try:
        if not vectorstore:
            return "⚠️ База знань недоступна. Спробуйте пізніше."
        
        print(f"🔍 Пошук у базі знань: {query}")
        
        # Извлекаем ключевые концепции из запроса
        query_concepts = extract_key_concepts(query)
        print(f"🎯 Виявлені концепції: {query_concepts}")
        
        # Выполняем поиск с большим количеством результатов
        results = vectorstore.similarity_search(query, k=15)
        
        if not results:
            return "📚 У базі знань не знайдено відповіді на це питання."
        
        # Вычисляем семантическую релевантность
        scored_results = []
        for result in results:
            score = calculate_semantic_relevance(result, query, query_concepts)
            scored_results.append((result, score))
            print(f"📄 {result.metadata.get('source', 'unknown')}: score={score}")
        
        # Сортируем по релевантности
        scored_results.sort(key=lambda x: x[1], reverse=True)
        
        # Берем только действительно релевантные результаты
        min_score = 50 if query_concepts else 20
        relevant_results = [result for result, score in scored_results if score >= min_score][:3]
        
        if not relevant_results:
            return "📚 Не знайдено релевантної інформації для вашого запиту. Можливо, потрібно перефразувати питання або звернутися безпосередньо до профспілки."
        
        # Формируем ответ
        response = "📖 Знайдена інформація з бази знань:\n\n"
        
        for i, result in enumerate(relevant_results, 1):
            source = result.metadata.get('source', 'Невідоме джерело')
            content = result.page_content.strip()
            
            # Ограничиваем длину контента
            if len(content) > 400:
                content = content[:400] + "..."
            
            response += f"📄 Джерело: {source}\n"
            response += f"{content}\n"
            
            if i < len(relevant_results):
                response += "\n" + "="*30 + "\n\n"
        
        return response
        
    except Exception as e:
        print(f"❌ DB error: {e}")
        return "⚠️ Сталася помилка при пошуку в базі знань."

def ask_gpt_with_smart_context(message):
    """GPT с улучшенным семантическим контекстом"""
    try:
        context = ""
        
        if vectorstore:
            try:
                # Извлекаем концепции из запроса
                query_concepts = extract_key_concepts(message)
                
                # Выполняем семантический поиск
                results = vectorstore.similarity_search(message, k=10)
                
                if results:
                    # Оцениваем семантическую релевантность
                    scored_results = []
                    for result in results:
                        score = calculate_semantic_relevance(result, message, query_concepts)
                        scored_results.append((result, score))
                    
                    # Берем только высокорелевантные результаты
                    min_score = 30 if query_concepts else 15
                    relevant_results = [result for result, score in scored_results if score >= min_score][:2]
                    
                    if relevant_results:
                        context = "\n\nРелевантна інформація з бази знань:\n"
                        for result in relevant_results:
                            source = result.metadata.get('source', 'документ')
                            content = result.page_content[:400]
                            context += f"З {source}: {content}...\n\n"
                    else:
                        print("⚠️ Не знайдено релевантного контексту")
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
