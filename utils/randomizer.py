import random
import time
from typing import List, Dict, Any


class Randomizer:
    """Утилиты для генерации случайных значений"""

    @staticmethod
    def get_random_interval(min_val: int, max_val: int) -> int:
        """Получение случайного интервала"""
        return random.randint(min_val, max_val)

    @staticmethod
    def get_random_percentage(min_percent: float, max_percent: float) -> float:
        """Получение случайного процента"""
        return random.uniform(min_percent, max_percent)

    @staticmethod
    def get_random_delay(min_seconds: float = 5.0, max_seconds: float = 15.0) -> float:
        """Получение случайной задержки"""
        return random.uniform(min_seconds, max_seconds)

    @staticmethod
    def get_random_address_from_list(addresses: List[str]) -> str:
        """Получение случайного адреса из списка"""
        return random.choice(addresses) if addresses else None

    @staticmethod
    def get_random_amount(balance: int, min_percent: float = 0.1, max_percent: float = 1.0) -> int:
        """Получение случайной суммы на основе баланса"""
        percentage = random.uniform(min_percent, max_percent)
        return int(balance * percentage / 100)

    @staticmethod
    def get_random_network(networks: List[Dict]) -> Dict:
        """Получение случайной сети"""
        return random.choice(networks) if networks else None

    @staticmethod
    def shuffle_list(items: List[Any]) -> List[Any]:
        """Перемешивание списка"""
        shuffled = items.copy()
        random.shuffle(shuffled)
        return shuffled

    @staticmethod
    def get_random_operation_type() -> str:
        """Получение случайного типа операции"""
        operations = ['transfer', 'swap', 'liquidity_add', 'liquidity_remove']
        return random.choice(operations)

    @staticmethod
    def weighted_choice(choices: Dict[str, int]) -> str:
        """Взвешенный случайный выбор на основе вероятностей"""
        if not choices:
            return None

        total = sum(choices.values())
        if total == 0:
            return random.choice(list(choices.keys()))

        r = random.uniform(0, total)
        current = 0

        for choice, weight in choices.items():
            current += weight
            if r <= current:
                return choice

        return list(choices.keys())[-1]  # fallback