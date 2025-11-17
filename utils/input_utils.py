import os
import sys
from getpass import getpass


def safe_getpass(prompt: str) -> str:
    """
    Безопасный ввод пароля/приватного ключа с обработкой для PyCharm
    """
    # Проверяем, запущено ли в PyCharm или есть проблемы с getpass
    is_pycharm = 'PYCHARM_HOSTED' in os.environ

    if is_pycharm or not sys.stdin.isatty():
        # В PyCharm или неинтерактивном режиме - используем альтернативный метод
        print(f"🚨 ВНИМАНИЕ: {prompt} (данные будут видны при вводе!)")
        print("✅ Убедитесь, что никто не смотрит через ваше плечо!")
        result = input(f"{prompt}: ").strip()

        # Пытаемся очистить ввод из истории консоли
        clear_console_line()

        return result
    else:
        # В нормальном терминале - используем стандартный getpass
        return getpass(prompt).strip()


def clear_console_line():
    """Попытка очистить предыдущую строку в консоли"""
    try:
        # ANSI escape codes для перемещения курсора и очистки строки
        print("\033[F\033[K", end="")
    except:
        pass  # Игнорируем ошибки если не поддерживается


def secure_input(prompt: str, is_sensitive: bool = False) -> str:
    """
    Универсальная функция для безопасного ввода
    """
    if is_sensitive:
        return safe_getpass(prompt)
    else:
        return input(prompt).strip()


def validate_ip_address(ip: str) -> bool:
    """Валидация IP адреса"""
    import re
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if re.match(pattern, ip):
        parts = ip.split('.')
        for part in parts:
            if not 0 <= int(part) <= 255:
                return False
        return True
    return False


def validate_port(port: str) -> bool:
    """Валидация порта"""
    try:
        port_num = int(port)
        return 1 <= port_num <= 65535
    except ValueError:
        return False