import aiohttp
import requests
import time
from web3 import Web3
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter


class ProxyManager:
    def __init__(self, proxy_config: dict = None):
        self.proxy_config = proxy_config
        self.logger = None
        self.last_request_time = 0
        self.request_count = 0
        self.rate_limit_reset = time.time()

    def set_logger(self, logger):
        """Установка логгера"""
        self.logger = logger

    def _check_rate_limit(self):
        """Проверка rate limit для Pharos (500 запросов в 5 минут)"""
        current_time = time.time()

        # Сбрасываем счетчик если прошло 5 минут
        if current_time - self.rate_limit_reset > 300:  # 5 минут
            self.request_count = 0
            self.rate_limit_reset = current_time

        # Проверяем не превышен ли лимит
        if self.request_count >= 500:
            wait_time = 300 - (current_time - self.rate_limit_reset)
            if self.logger:
                self.logger.warning(f"⚠️ Rate limit reached. Waiting {wait_time:.1f}s")
            time.sleep(max(wait_time, 1))
            self.request_count = 0
            self.rate_limit_reset = time.time()

        self.request_count += 1
        self.last_request_time = current_time

    def create_web3_instance(self, rpc_url: str) -> Web3:
        """Создание экземпляра Web3 с прокси и rate limiting"""
        # Проверяем rate limit для Pharos
        if 'atlantic.dplabs-internal.com' in rpc_url:
            self._check_rate_limit()

        if self.proxy_config and self._validate_proxy_config():
            # Создаем сессию с прокси и retry стратегией
            session = requests.Session()

            # Настраиваем retry стратегию
            retry_strategy = Retry(
                total=3,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
                backoff_factor=1
            )

            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)

            # Настраиваем прокси
            proxy_url = self._build_proxy_url()
            session.proxies = {
                'http': proxy_url,
                'https': proxy_url
            }

            # Создаем провайдер с кастомной сессией
            from web3 import HTTPProvider
            provider = HTTPProvider(rpc_url, session=session)
            web3 = Web3(provider)

        else:
            # Без прокси
            web3 = Web3(Web3.HTTPProvider(rpc_url))

        # Для сетей PoA (как Pharos) - используем новый способ
        self._inject_poa_middleware(web3)

        return web3

    def _inject_poa_middleware(self, web3: Web3):
        """Инжект middleware для сетей PoA"""
        try:
            # Пробуем новый импорт для современных версий web3.py
            from web3.middleware import extra_poa_middleware
            web3.middleware_onion.inject(extra_poa_middleware, layer=0)
        except ImportError:
            try:
                # Старый импорт для обратной совместимости
                from web3.middleware import geth_poa_middleware
                web3.middleware_onion.inject(geth_poa_middleware, layer=0)
            except ImportError:
                # Если middleware не найдено, просто пропускаем (это не критично)
                pass  # Просто пропускаем без предупреждения

    def _build_proxy_url(self) -> str:
        """Построение URL для прокси"""
        if not self.proxy_config:
            return ""

        ip = self.proxy_config.get('ip', '')
        port = self.proxy_config.get('port', '')
        username = self.proxy_config.get('username', '')
        password = self.proxy_config.get('password', '')

        if username and password:
            return f"http://{username}:{password}@{ip}:{port}"
        else:
            return f"http://{ip}:{port}"

    def _validate_proxy_config(self) -> bool:
        """Валидация конфигурации прокси"""
        if not self.proxy_config:
            return False

        required_fields = ['ip', 'port']
        for field in required_fields:
            if not self.proxy_config.get(field):
                if self.logger:
                    self.logger.warning(f"⚠️ Proxy config missing required field: {field}")
                return False

        return True

    async def test_connection(self) -> bool:
        """Тестирование подключения прокси"""
        if not self.proxy_config:
            return True

        try:
            proxy_url = self._build_proxy_url()

            async with aiohttp.ClientSession() as session:
                async with session.get('http://httpbin.org/ip', proxy=proxy_url, timeout=10) as response:
                    if response.status == 200:
                        if self.logger:
                            self.logger.info(f"✅ Proxy connection successful: {self.proxy_config.get('ip')}")
                        return True
                    else:
                        if self.logger:
                            self.logger.warning(f"⚠️ Proxy connection failed with status: {response.status}")
                        return False
        except Exception as e:
            if self.logger:
                self.logger.error(f"❌ Proxy connection error: {e}")
            return False