import os
import base64
import re
from pathlib import Path
from typing import List, Optional
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv
from eth_account import Account


class SecurityManager:
    def __init__(self, encryption_key: str = None, fallback_keys: Optional[List[str]] = None):
        # Используем ключ из переменных окружения
        self.encryption_key = encryption_key or os.getenv('ENCRYPTION_KEY')
        if not self.encryption_key:
            raise ValueError("ENCRYPTION_KEY is not set. Call setup_secure_environment() first.")

        # Дополняем ключ до 32 байт если нужно
        if len(self.encryption_key) < 32:
            self.encryption_key = self.encryption_key.ljust(32, '0')
        elif len(self.encryption_key) > 32:
            self.encryption_key = self.encryption_key[:32]

        # Кодируем в base64 для Fernet
        key_b64 = base64.urlsafe_b64encode(self.encryption_key.encode())
        self.cipher_suite = Fernet(key_b64)

        self.legacy_ciphers = []
        self.legacy_warning_emitted = False

        legacy_keys = fallback_keys[:] if fallback_keys else []

        legacy_env = os.getenv('LEGACY_ENCRYPTION_KEYS')
        if legacy_env:
            legacy_keys.extend([key.strip() for key in legacy_env.split(',') if key.strip()])

        default_legacy = "test_encryption_key_32_bytes_long!"
        if default_legacy not in legacy_keys:
            legacy_keys.append(default_legacy)

        for legacy_key in legacy_keys:
            if not legacy_key:
                continue
            normalized = legacy_key
            if len(normalized) < 32:
                normalized = normalized.ljust(32, '0')
            elif len(normalized) > 32:
                normalized = normalized[:32]
            legacy_b64 = base64.urlsafe_b64encode(normalized.encode())
            try:
                self.legacy_ciphers.append(Fernet(legacy_b64))
            except Exception:
                continue

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
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_key.encode())

        try:
            decrypted = self.cipher_suite.decrypt(encrypted_bytes)
            return self._ensure_hex_prefix(decrypted.decode())
        except InvalidToken:
            for cipher in self.legacy_ciphers:
                try:
                    decrypted = cipher.decrypt(encrypted_bytes)
                    if not self.legacy_warning_emitted:
                        print("⚠️  Using legacy encryption key for wallet data. "
                              "Перешифруйте кошельки с новым ENCRYPTION_KEY как можно скорее.")
                        self.legacy_warning_emitted = True
                    return self._ensure_hex_prefix(decrypted.decode())
                except InvalidToken:
                    continue
            raise ValueError("Decryption failed: invalid encryption key")
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")

    def _ensure_hex_prefix(self, private_key: str) -> str:
        if not private_key.startswith('0x'):
            return '0x' + private_key
        return private_key

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


_security_manager = None


def _get_security_manager() -> SecurityManager:
    """Ленивая инициализация менеджера безопасности"""
    global _security_manager
    if _security_manager is None:
        setup_secure_environment()
        _security_manager = SecurityManager()
    return _security_manager


# Функции для прямого импорта
def encrypt_private_key(private_key: str) -> str:
    """Шифрование приватного ключа"""
    return _get_security_manager().encrypt_private_key(private_key)


def decrypt_private_key(encrypted_key: str) -> str:
    """Дешифрование приватного ключа"""
    return _get_security_manager().decrypt_private_key(encrypted_key)


def validate_private_key(private_key: str) -> bool:
    """Валидация приватного ключа"""
    return _get_security_manager().validate_private_key(private_key)


def secure_log(message: str) -> str:
    """Безопасное логирование"""
    return _get_security_manager().secure_log(message)


def generate_secure_key() -> str:
    """Генерация безопасного ключа шифрования"""
    import secrets
    return secrets.token_hex(32)  # 64 hex characters = 32 bytes


def setup_secure_environment():
    """Настройка безопасного окружения"""
    load_dotenv()

    if os.getenv('ENCRYPTION_KEY'):
        return

    print("⚠️  ENCRYPTION_KEY not found in environment variables")
    print("🔑 Generating new encryption key and saving it to .env ...")

    new_key = generate_secure_key()
    os.environ['ENCRYPTION_KEY'] = new_key

    env_path = Path('.env')
    try:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        with env_path.open('a') as env_file:
            env_file.write(f"\nENCRYPTION_KEY={new_key}\n")
        print(f"✅ ENCRYPTION_KEY saved to {env_path.resolve()}")
    except Exception as exc:
        print(f"⚠️  Failed to write ENCRYPTION_KEY to .env: {exc}")

    print("🚨 WARNING: Keep the generated key safe. Losing it will make existing wallets unreadable!")


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
    test_encryption_performance()
# Автоматическая настройка при импорте
setup_secure_environment()
