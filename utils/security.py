import os
import base64
import re
from cryptography.fernet import Fernet
from eth_account import Account


class SecurityManager:
    def __init__(self, encryption_key: str = None):
        # Используем ключ из переменных окружения или генерируем по умолчанию
        self.encryption_key = encryption_key or os.getenv('ENCRYPTION_KEY')
        if not self.encryption_key:
            # Для тестов создаем ключ по умолчанию
            self.encryption_key = "test_encryption_key_32_bytes_long!"

        # Дополняем ключ до 32 байт если нужно
        if len(self.encryption_key) < 32:
            self.encryption_key = self.encryption_key.ljust(32, '0')
        elif len(self.encryption_key) > 32:
            self.encryption_key = self.encryption_key[:32]

        # Кодируем в base64 для Fernet
        key_b64 = base64.urlsafe_b64encode(self.encryption_key.encode())
        self.cipher_suite = Fernet(key_b64)

    def encrypt_private_key(self, private_key: str) -> str:
        """
        Шифрование приватного ключа
        """
        try:
            # Нормализуем формат приватного ключа
            private_key = self._normalize_private_key(private_key)

            # Шифруем
            encrypted = self.cipher_suite.encrypt(private_key.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            raise ValueError(f"Encryption failed: {e}")

    def decrypt_private_key(self, encrypted_key: str) -> str:
        """
        Дешифрование приватного ключа
        """
        try:
            # Декодируем из base64
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_key.encode())
            decrypted = self.cipher_suite.decrypt(encrypted_bytes)
            private_key = decrypted.decode()

            # Добавляем 0x если нужно
            if not private_key.startswith('0x'):
                private_key = '0x' + private_key

            return private_key
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")

    def _normalize_private_key(self, private_key: str) -> str:
        """Нормализация формата приватного ключа"""
        # Убираем пробелы и переводы строк
        private_key = private_key.strip()

        # Убираем префикс 0x если есть
        if private_key.startswith('0x'):
            private_key = private_key[2:]

        # Проверяем длину (64 hex символа)
        if len(private_key) != 64:
            raise ValueError("Private key must be 64 hexadecimal characters")

        # Проверяем что это hex строка
        if not re.match(r'^[0-9a-fA-F]{64}$', private_key):
            raise ValueError("Private key must contain only hexadecimal characters")

        return private_key

    def validate_private_key(self, private_key: str) -> bool:
        """
        Валидация приватного ключа
        """
        try:
            # Нормализуем и проверяем формат
            normalized_key = self._normalize_private_key(private_key)

            # Проверяем что можно создать аккаунт
            test_key = '0x' + normalized_key
            account = Account.from_key(test_key)
            return bool(account.address)
        except:
            return False

    def secure_log(self, message: str) -> str:
        """
        Безопасное логирование - скрывает приватные данные
        """
        secure_message = message

        # Скрываем приватные ключи
        if 'private_key' in message.lower():
            secure_message = "***PRIVATE_KEY_REDACTED***"

        # Скрываем seed фразы
        if 'seed' in message.lower() or 'mnemonic' in message.lower():
            secure_message = "***SEED_PHRASE_REDACTED***"

        return secure_message


# Создаем глобальный экземпляр для удобства
security_manager = SecurityManager()


# Функции для прямого импорта
def encrypt_private_key(private_key: str) -> str:
    """Шифрование приватного ключа"""
    return security_manager.encrypt_private_key(private_key)


def decrypt_private_key(encrypted_key: str) -> str:
    """Дешифрование приватного ключа"""
    return security_manager.decrypt_private_key(encrypted_key)


def validate_private_key(private_key: str) -> bool:
    """Валидация приватного ключа"""
    return security_manager.validate_private_key(private_key)


def secure_log(message: str) -> str:
    """Безопасное логирование"""
    return security_manager.secure_log(message)


def generate_secure_key() -> str:
    """Генерация безопасного ключа шифрования"""
    import secrets
    return secrets.token_hex(32)  # 64 hex characters = 32 bytes


def setup_secure_environment():
    """Настройка безопасного окружения"""
    if not os.getenv('ENCRYPTION_KEY'):
        print("⚠️  ENCRYPTION_KEY not found in environment variables")
        print("🔑 Generating temporary encryption key...")

        # Генерируем временный ключ (в продакшене должен быть в .env)
        temp_key = generate_secure_key()
        os.environ['ENCRYPTION_KEY'] = temp_key

        print("✅ Temporary encryption key generated")
        print("🚨 WARNING: For production use, set ENCRYPTION_KEY in .env file!")


def test_encryption_performance():
    """Тест производительности шифрования"""
    import time
    test_key = "0x" + "a" * 64

    start_time = time.time()
    encrypted = encrypt_private_key(test_key)
    encryption_time = time.time() - start_time

    start_time = time.time()
    decrypted = decrypt_private_key(encrypted)
    decryption_time = time.time() - start_time

    print(f"🔐 Encryption: {encryption_time * 1000:.2f}ms")
    print(f"🔓 Decryption: {decryption_time * 1000:.2f}ms")
    print(f"✅ Correctness: {test_key == decrypted}")


if __name__ == "__main__":
    test_security()
    test_encryption_performance()
# Автоматическая настройка при импорте
setup_secure_environment()