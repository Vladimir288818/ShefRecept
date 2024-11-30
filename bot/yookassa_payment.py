# yookassa_payment
import os
import uuid
import logging
from typing import Union, Optional, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal
from yookassa import Configuration, Payment
from yookassa.domain.notification import WebhookNotification
from yookassa.domain.response import PaymentResponse
from yookassa.domain.common import ConfirmationType
import base64
import requests
import asyncio
from aiohttp import ClientSession, ClientTimeout

logging.basicConfig(
   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
   level=logging.INFO
)
logger = logging.getLogger(__name__)

shop_id = "494677"
secret_key = "test_bClYlbKXCYhQtbbgBcH59Pk0CzTub3y4bsyH1yVKH6E"
TIMEOUT_SECONDS = 5  # Таймаут для запросов

Configuration.configure(
   account_id=shop_id,
   secret_key=secret_key
)

is_test_mode = True
class PaymentError(Exception):
   """Базовый класс для ошибок платежей"""
   pass

class PaymentCreationError(PaymentError):
   """Ошибка при создании платежа"""
   pass

class PaymentStatusError(PaymentError):
   """Ошибка при проверке статуса платежа"""
   pass

class YooKassaPayment:
   def __init__(self):
       """Инициализация платежной системы YooKassa"""
       try:
           if not Configuration.account_id or not Configuration.secret_key:
               raise PaymentError("Missing YooKassa credentials")
           logger.info("YooKassa payment system initialized successfully")
       except Exception as e:
           raise PaymentError(f"Payment system initialization failed: {e}")

   @staticmethod
   def _generate_headers() -> Dict[str, str]:
       """Генерация заголовков для запросов к YooKassa"""
       auth_header = base64.b64encode(f"{shop_id}:{secret_key}".encode()).decode()
       idempotence_key = str(uuid.uuid4())
       return {
           "Authorization": f"Basic {auth_header}",
           "Content-Type": "application/json",
           "Idempotence-Key": idempotence_key
       }

   @staticmethod
   def _format_datetime(dt: datetime) -> str:
       """Форматирует datetime в строку"""
       return dt.strftime('%Y-%m-%d %H:%M:%S')
   async def check_pending_payments(
       self,
       user_id: int,
       subscription_type: str,
       duration: int
   ) -> Optional[Dict[str, Any]]:
       """Асинхронная проверка наличия незавершенных платежей для пользователя"""
       try:
           logger.info(f"Checking pending payments for user {user_id}")
           headers = self._generate_headers()
           current_time = datetime.now()
           one_hour_ago = (current_time - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

           timeout = ClientTimeout(total=TIMEOUT_SECONDS)
           async with ClientSession(timeout=timeout) as session:
               async with session.get(
                   "https://api.yookassa.ru/v3/payments",
                   headers=headers,
                   params={"created_at.gte": one_hour_ago}
               ) as response:
                   if response.status != 200:
                       logger.error(f"Failed to get payments: {await response.text()}")
                       return None

                   payments = (await response.json()).get("items", [])
                   
                   # Ищем незавершенные платежи пользователя
                   for payment in payments:
                       metadata = payment.get("metadata", {})
                       if (payment["status"] in ["pending", "waiting_for_capture"] and
                           metadata.get("user_id") == str(user_id) and
                           metadata.get("subscription_type") == subscription_type and
                           metadata.get("duration") == str(duration)):
                           logger.info(f"Found pending payment {payment['id']} for user {user_id}")
                           return payment

           return None

       except asyncio.TimeoutError:
           logger.warning(f"Timeout while checking payments for user {user_id}")
           return None
       except Exception as e:
           logger.error(f"Error checking pending payments: {e}")
           return None

   def create_payment(
        self,
        amount: Union[int, float, Decimal],
        description: str,
        user_id: int,
        subscription_type: str,
        duration: int,
        return_url: str
    ) -> Dict[str, Any]:
        """Создает платеж в системе YooKassa"""
        try:
            # Пытаемся проверить существующие платежи с таймаутом
            try:
                loop = asyncio.get_event_loop()
                existing_payment = loop.run_until_complete(
                    self.check_pending_payments(user_id, subscription_type, duration)
                )
                if existing_payment:
                    logger.info(f"Using existing payment {existing_payment['id']} for user {user_id}")
                    return {
                        "payment_id": existing_payment["id"],
                        "status": existing_payment["status"],
                        "paid": existing_payment["paid"],
                        "amount": existing_payment["amount"]["value"],
                        "currency": existing_payment["amount"]["currency"],
                        "confirmation_url": existing_payment["confirmation"]["confirmation_url"],
                        "created_at": existing_payment.get("created_at"),
                        "metadata": existing_payment.get("metadata", {})
                    }
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"Failed to check existing payments, proceeding with new payment: {e}")

            # Создаем новый платеж
            logger.info("Creating payment...")
            headers = self._generate_headers()
            payment_data = {
                "amount": {"value": f"{float(amount):.2f}", "currency": "RUB"},
                "confirmation": {"type": "redirect", "return_url": return_url},
                "capture": True,
                "description": description,
                "metadata": {
                    "user_id": str(user_id),
                    "subscription_type": subscription_type,
                    "duration": str(duration),
                    "created_at": self._format_datetime(datetime.now()),
                    "test_mode": is_test_mode
                }
            }

            logger.info(f"Payment data: {payment_data}")
            response = requests.post(
                url="https://api.yookassa.ru/v3/payments",
                json=payment_data,
                headers=headers,
                timeout=TIMEOUT_SECONDS
            )

            if response.status_code != 200:
                raise PaymentCreationError(f"Failed to create payment: {response.json()}")

            payment_info = response.json()
            logger.info(f"Payment created successfully: {payment_info['id']}")
            return {
                "payment_id": payment_info["id"],
                "status": payment_info["status"],
                "paid": payment_info["paid"],
                "amount": payment_info["amount"]["value"],
                "currency": payment_info["amount"]["currency"],
                "confirmation_url": payment_info["confirmation"]["confirmation_url"],
                "created_at": payment_info.get("created_at"),
                "metadata": payment_info.get("metadata", {})
            }

        except Exception as e:
            logger.error(f"Error creating payment: {e}")
            raise PaymentCreationError(f"Failed to create payment: {e}")
   def check_payment_status(self, payment_id: str) -> Dict[str, Any]:
       """Проверяет статус платежа"""
       try:
           logger.info(f"Checking payment status for payment_id: {payment_id}")
           headers = self._generate_headers()
           response = requests.get(
               f"https://api.yookassa.ru/v3/payments/{payment_id}",
               headers=headers,
               timeout=TIMEOUT_SECONDS
           )

           if response.status_code != 200:
               raise PaymentStatusError(f"Failed to check payment status: {response.json()}")

           payment_info = response.json()
           logger.info(f"Payment status checked successfully: {payment_info['status']}")
           return {
               "payment_id": payment_info["id"],
               "status": payment_info["status"],
               "paid": payment_info["paid"],
               "amount": payment_info["amount"]["value"],
               "currency": payment_info["amount"]["currency"],
               "metadata": payment_info.get("metadata", {})
           }
       except Exception as e:
           logger.error(f"Error checking payment status: {e}")
           raise PaymentStatusError(f"Failed to check payment status: {e}")

   def handle_notification(self, notification_data: Dict[str, Any]) -> Dict[str, Any]:
       """
       Обрабатывает уведомление от YooKassa
       Args:
           notification_data: Данные, полученные в теле уведомления
       Returns:
           Dict с информацией о платеже
       """
       try:
           notification = WebhookNotification(notification_data)
           payment = notification.object

           logger.info(f"Notification received for payment ID: {payment.id}")
           logger.info(f"Payment status: {payment.status}")
           logger.info(f"Paid: {payment.paid}")

           return {
               "payment_id": payment.id,
               "status": payment.status,
               "paid": payment.paid,
               "amount": payment.amount.value,
               "currency": payment.amount.currency,
               "metadata": payment.metadata,
               "created_at": payment.created_at
           }
       except Exception as e:
           logger.error(f"Error processing notification: {e}")
           raise PaymentError(f"Failed to handle notification: {e}")

def test_payment():
   """Тестовый метод для проверки создания платежа"""
   try:
       logger.info("Creating a test payment...")
       headers = YooKassaPayment._generate_headers()
       payment_data = {
           "amount": {
               "value": "10.00",
               "currency": "RUB"
           },
           "confirmation": {
               "type": "redirect",
               "return_url": "https://example.com"
           },
           "capture": True,
           "description": "Тестовый платеж",
           "metadata": {
               "test_mode": True
           }
       }
       response = requests.post(
           url="https://api.yookassa.ru/v3/payments",
           json=payment_data,
           headers=headers,
           timeout=TIMEOUT_SECONDS
       )
       if response.status_code != 200:
           raise PaymentCreationError(f"Failed to create test payment: {response.json()}")
       payment_info = response.json()
       logger.info(f"Test payment created successfully: {payment_info['id']}")
       logger.info(f"Confirmation URL: {payment_info['confirmation']['confirmation_url']}")
       return payment_info
   except Exception as e:
       logger.error(f"Error during test payment: {e}")
       raise PaymentCreationError(f"Test payment failed: {e}")

if __name__ == "__main__":
   test_payment()