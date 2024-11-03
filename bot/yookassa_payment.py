# bot/yookassa_payment.py
import os
from yookassa import Configuration, Payment

# Настройка данных ЮKассы
Configuration.account_id = os.getenv("YOOKASSA_SHOP_ID")
Configuration.secret_key = os.getenv("YOOKASSA_SECRET_KEY")

def create_payment(amount, description, user_id):
    payment = Payment.create({
        "amount": {
            "value": str(amount),
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": "https://ваш_сайт.ru/success"
        },
        "capture": True,
        "description": description,
        "metadata": {
            "user_id": user_id
        }
    })
    return payment