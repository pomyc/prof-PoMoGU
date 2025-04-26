from datetime import datetime
from telegram import ReplyKeyboardRemove

def calculate_seniority(start_date_str, end_date_str=None):
    try:
        start_date = datetime.strptime(start_date_str, "%d.%m.%Y")
        if end_date_str:
            end_date = datetime.strptime(end_date_str, "%d.%m.%Y")
        else:
            end_date = datetime.today()

        delta = end_date - start_date
        days = delta.days

        years = days // 365
        months = (days % 365) // 30
        remaining_days = (days % 365) % 30

        return f"✅ Ваш стаж становить: {years} років {months} місяців {remaining_days} днів."
    except Exception as e:
        return f"⚠️ Помилка обробки дат. Переконайтесь, що ви ввели їх у форматі ДД.ММ.РРРР.\nДеталі: {e}"

# Приклад використання:
if __name__ == "__main__":
    print(calculate_seniority("01.09.2015", "24.04.2025"))