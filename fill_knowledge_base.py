import chromadb
from chromadb.config import Settings

# Створюємо клієнт для ChromaDB
chroma_client = chromadb.Client(Settings(
    persist_directory="./knowledge_base",
    chroma_db_impl="duckdb+parquet"
))

# Створюємо або відкриваємо колекцію
collection = chroma_client.get_or_create_collection(name="prof_union_knowledge")

# Сюди додаємо документи профспілки вручну
documents = [
    "Статут профспілки: Рішення про затвердження гімну приймається на з'їзді профспілки.",
    "Порядок виборів: Делегати обираються відкритим голосуванням за квотою, встановленою рішенням профкому.",
    "Рекомендації: Голова профспілки відповідає за організацію загальних зборів членів профспілки.",
    "Галузева угода: Роботодавець забезпечує мінімальні гарантії з оплати праці згідно галузевої угоди."
]

# Для унікальних ID
ids = [f"id{i}" for i in range(len(documents))]

# Додаємо документи до колекції
collection.add(
    documents=documents,
    metadatas=[{"source": "internal"}] * len(documents),
    ids=ids
)

# Зберігаємо базу
chroma_client.persist()

print("✅ Knowledge base created successfully!")
