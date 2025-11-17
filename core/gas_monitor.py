import asyncio
import time
import aiohttp
from web3 import Web3
from utils.logger import setup_logger


class GasMonitor:
    def __init__(self, config):
        self.config = config
        self.logger = setup_logger("GasMonitor")
        self.gas_price_cache = {}
        self.last_update = 0
        self.cache_timeout = 30  # секунды

    async def get_optimal_gas_price(self, network_name: str = None) -> int:
        """Получение оптимальной цены газа"""
        try:
            current_time = time.time()

            # Кэширование
            if (network_name in self.gas_price_cache and
                    current_time - self.gas_price_cache[network_name]['timestamp'] < self.cache_timeout):
                return self.gas_price_cache[network_name]['gas_price']

            # Получаем данные из сети
            gas_price = await self._fetch_network_gas_price(network_name)

            # Добавляем маржу для надежности
            optimal_price = int(gas_price * 1.15)  # +15%

            self.gas_price_cache[network_name] = {
                'gas_price': optimal_price,
                'timestamp': current_time
            }

            self.logger.info(f"⛽ Optimal gas price for {network_name}: {Web3.from_wei(optimal_price, 'gwei'):.2f} Gwei")
            return optimal_price

        except Exception as e:
            self.logger.error(f"❌ Gas monitoring error: {e}")
            # Возвращаем безопасное значение по умолчанию
            return Web3.to_wei('10', 'gwei')

    async def _fetch_network_gas_price(self, network_name: str) -> int:
        """Получение цены газа из сети"""
        try:
            network = self.config.get_network_by_name(network_name)
            if not network:
                return Web3.to_wei('10', 'gwei')

            web3 = Web3(Web3.HTTPProvider(network['rpc_url']))
            gas_price = web3.eth.gas_price

            self.logger.debug(f"🔍 Current gas price in {network_name}: {Web3.from_wei(gas_price, 'gwei'):.2f} Gwei")
            return gas_price

        except Exception as e:
            self.logger.warning(f"⚠️ Failed to fetch gas price from {network_name}: {e}")
            return Web3.to_wei('10', 'gwei')  # Fallback

    def get_gas_limits(self, transaction_type: str = "transfer") -> dict:
        """Получить лимиты газа для разных типов транзакций"""
        gas_limits = {
            "transfer": 21000,  # Базовая транзакция
            "erc20_transfer": 65000,  # ERC20 перевод
            "approve": 45000,  # Approve токенов
            "swap": 200000,  # Своп в DEX
            "complex": 300000  # Сложные операции
        }
        return {
            "gas_limit": gas_limits.get(transaction_type, 21000),
            "max_priority_fee": Web3.to_wei('1', 'gwei'),
            "max_fee_multiplier": 1.2
        }