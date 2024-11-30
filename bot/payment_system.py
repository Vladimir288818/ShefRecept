#payment_system.py
import logging
from datetime import datetime
from typing import Dict, Optional, Any
from yookassa import Configuration, Payment
from yookassa.domain.common import ConfirmationType
from yookassa.domain.response import PaymentResponse
import uuid
from decimal import Decimal

logger = logging.getLogger(__name__)

class PaymentError(Exception):
    """Базовый класс для ошибок платежной системы"""
    pass

class PaymentCreationError(PaymentError):
    """Ошибка при создании платежа"""
    pass

class PaymentStatusError(PaymentError):
    """Ошибка при проверке статуса платежа"""
    pass

class PaymentSystem:
    def __init__(self, shop_id: str, secret_key: str):
        """Инициализация платежной системы
        
        Args:
            shop_id (str): Идентификатор магазина в ЮKassa
            secret_key (str): Секретный ключ магазина
        """
        try:
            Configuration.account_id = shop_id
            Configuration.secret_key = secret_key
            logger.info("PaymentSystem initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize PaymentSystem: {e}")
            raise PaymentError("Payment system initialization failed")

    @staticmethod
    def _format_datetime(dt: Optional[datetime]) -> Optional[str]:
        """Форматирует datetime в строку, совместимую с SQLite
        
        Args:
            dt: datetime объект для форматирования

        Returns:
            str: Отформатированная дата и время или None
        """
        return dt.strftime('%Y-%m-%d %H:%M:%S') if dt else None

    def create_payment(
        self, 
        amount: int, 
        description: str,
        user_id: int,
        subscription_type: str,
        duration: int,
        return_url: str
    ) -> Dict[str, str]:
        """Создание нового платежа
        
        Args:
            amount (int): Сумма платежа
            description (str): Описание платежа
            user_id (int): ID пользователя
            subscription_type (str): Тип подписки
            duration (int): Длительность подписки в месяцах
            return_url (str): URL для возврата после оплаты

        Returns:
            Dict[str, str]: Информация о созданном платеже

        Raises:
            PaymentCreationError: При ошибке создания платежа
        """
        try:
            transaction_id = str(uuid.uuid4())
            payment_data = {
                "amount": {
                    "value": str(Decimal(amount).quantize(Decimal('0.00'))),
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": ConfirmationType.REDIRECT,
                    "return_url": return_ur1,
                },
                "capture": True,
                "description": description,
                "metadata": {
                    "transaction_id": transaction_id,
                    "user_id": str(user_id),
                    "subscription_type": subscription_type,
                    "duration": str(duration),
                    "created_at": self._format_datetime(datetime.now())
                }
            }

            payment: PaymentResponse = Payment.create(payment_data)
            
            logger.info(f"Payment created successfully: {payment.id}")
            return {
                "payment_id": payment.id,
                "payment_url": payment.confirmation.confirmation_url,
                "transaction_id": transaction_id,
                "amount": payment.amount.value,
                "currency": payment.amount.currency,
                "status": payment.status,
                "created_at": self._format_datetime(payment.created_at)
            }

        except Exception as e:
            logger.error(f"Payment creation failed: {e}")
            raise PaymentCreationError(f"Failed to create payment: {e}")

    def check_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """Проверка статуса платежа
        
        Args:
            payment_id (str): Идентификатор платежа

        Returns:
            Dict[str, Any]: Информация о статусе платежа

        Raises:
            PaymentStatusError: При ошибке получения статуса платежа
        """
        try:
            payment: PaymentResponse = Payment.find_one(payment_id)
            
            status_info = {
                "status": payment.status,
                "paid": payment.paid,
                "amount": payment.amount.value,
                "currency": payment.amount.currency,
                "metadata": payment.metadata,
                "created_at": self._format_datetime(payment.created_at),
                "captured_at": self._format_datetime(payment.captured_at)
            }
            
            logger.info(f"Payment status checked successfully: {payment_id}")
            return status_info

        except Exception as e:
            logger.error(f"Failed to check payment status: {e}")
            raise PaymentStatusError(f"Failed to check payment status: {e}")

    def cancel_payment(self, payment_id: str) -> Dict[str, Any]:
        """Отмена платежа
        
        Args:
            payment_id (str): Идентификатор платежа

        Returns:
            Dict[str, Any]: Информация об отмененном платеже

        Raises:
            PaymentError: При ошибке отмены платежа
        """
        try:
            payment: PaymentResponse = Payment.cancel(payment_id)
            
            cancel_info = {
                "status": payment.status,
                "cancelled_at": self._format_datetime(payment.cancelled_at),
                "metadata": payment.metadata
            }
            
            logger.info(f"Payment cancelled successfully: {payment_id}")
            return cancel_info

        except Exception as e:
            logger.error(f"Failed to cancel payment: {e}")
            raise PaymentError(f"Failed to cancel payment: {e}")

    def get_payment_info(self, payment_id: str) -> Dict[str, Any]:
        """Получение полной информации о платеже
        
        Args:
            payment_id (str): Идентификатор платежа

        Returns:
            Dict[str, Any]: Полная информация о платеже

        Raises:
            PaymentError: При ошибке получения информации о платеже
        """
        try:
            payment: PaymentResponse = Payment.find_one(payment_id)
            
            payment_info = {
                "payment_id": payment.id,
                "status": payment.status,
                "paid": payment.paid,
                "amount": payment.amount.value,
                "currency": payment.amount.currency,
                "description": payment.description,
                "metadata": payment.metadata,
                "created_at": self._format_datetime(payment.created_at),
                "captured_at": self._format_datetime(payment.captured_at),
                "cancelled_at": self._format_datetime(payment.cancelled_at),
                "refundable": payment.refundable
            }
            
            logger.info(f"Payment info retrieved successfully: {payment_id}")
            return payment_info

        except Exception as e:
            logger.error(f"Failed to get payment info: {e}")
            raise PaymentError(f"Failed to get payment info: {e}")

    def is_payment_successful(self, payment_id: str) -> bool:
        """Проверка успешности платежа
        
        Args:
            payment_id (str): Идентификатор платежа

        Returns:
            bool: True если платеж успешен, False в противном случае
        """
        try:
            payment_info = self.check_payment_status(payment_id)
            return payment_info["status"] == "succeeded" and payment_info["paid"]
        except Exception as e:
            logger.error(f"Failed to check payment success: {e}")
            return False