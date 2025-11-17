import logging
import sys
from pathlib import Path
import sqlite3
from datetime import datetime

# Глобальный словарь для отслеживания инициализированных логгеров
_initialized_loggers = set()


def setup_logger(name: str = None) -> logging.Logger:
    """Настройка системы логирования без дублирования"""
    if name is None:
        name = __name__

    logger = logging.getLogger(name)

    # Если логгер уже инициализирован - возвращаем его
    if name in _initialized_loggers:
        return logger

    # Устанавливаем уровень
    logger.setLevel(logging.INFO)

    # ✅ ПРОВЕРЯЕМ, ЧТОБЫ НЕ ДОБАВЛЯТЬ ОБРАБОТЧИКИ ПОВТОРНО
    if not logger.handlers:
        # Форматтер
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Консольный handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Файловый handler
        log_file = Path("logs/evm_tester.log")
        log_file.parent.mkdir(exist_ok=True)

        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Помечаем как инициализированный
    _initialized_loggers.add(name)

    return logger


class DatabaseLogger:
    """Логирование транзакций в SQLite"""

    def __init__(self, db_path: str = "data/transactions.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self.init_database()

    def init_database(self):
        """Инициализация таблиц базы данных"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wallet_address TEXT,
                    operation_type TEXT,
                    network TEXT,
                    amount TEXT,
                    token_in TEXT,
                    token_out TEXT,
                    tx_hash TEXT,
                    status TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS wallet_balances (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wallet_address TEXT,
                    network TEXT,
                    balance_eth TEXT,
                    balance_tokens TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')