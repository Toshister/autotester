import os
import json
from typing import Dict, List
from dotenv import load_dotenv
from utils.logger import setup_logger
from utils.randomizer import Randomizer

load_dotenv()


class Config:
    def __init__(self, config_path: str = "config/config.json"):
        self.logger = setup_logger("Config")
        self.config_path = config_path
        self.wallets = []
        self.networks = []
        self.operations_config = {}
        self.tokens_config = {}
        self.config_data = {}  # ✅ ДОБАВЛЕНО ДЛЯ ДОСТУПА К ВСЕМ ДАННЫМ

        # Создаем папку config если её нет
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        self.load_config()

    def load_config(self):
        """Загрузка конфигурации из JSON файла с улучшенной обработкой ошибок"""
        try:
            if not os.path.exists(self.config_path):
                self.logger.warning(f"⚠️ Config file not found: {self.config_path}")
                self.create_default_config()
                return

            with open(self.config_path, 'r') as f:
                self.config_data = json.load(f)  # ✅ СОХРАНЯЕМ ВСЕ ДАННЫЕ

            # Безопасная загрузка с проверками
            self.wallets = self._safe_get(self.config_data, 'wallets', [])
            self.networks = self._safe_get(self.config_data, 'networks', [])
            self.operations_config = self._safe_get(self.config_data, 'operations', {})
            self.tokens_config = self._safe_get(self.config_data, 'tokens', {})

            # Обрабатываем кошельки и сети
            self.wallets = self._process_wallets_config(self.wallets)
            self.networks = self._process_networks_config(self.networks)

            self.logger.info(f"✅ Configuration loaded: {len(self.wallets)} wallets, {len(self.networks)} networks")

            # Логируем информацию о сетях и токенах
            for network in self.networks:
                network_tokens = self.get_tokens_for_network(network['name'])
                self.logger.info(
                    f"🌐 Network: {network['name']} (ChainID: {network['chain_id']}) - Tokens: {len(network_tokens)}")

        except json.JSONDecodeError as e:
            self.logger.error(f"❌ JSON decode error in config: {e}")
            self.logger.info("🔄 Creating backup and generating new config...")
            self._backup_and_create_config()
        except Exception as e:
            self.logger.error(f"❌ Failed to load configuration: {e}")
            self._backup_and_create_config()

    def _safe_get(self, data, key, default):
        """Безопасное получение значения из словаря"""
        if data is None:
            return default
        return data.get(key, default)

    def _backup_and_create_config(self):
        """Создание бэкапа поврежденного конфига и генерация нового"""
        try:
            # Создаем бэкап поврежденного файла
            if os.path.exists(self.config_path):
                backup_path = self.config_path + '.backup'
                os.rename(self.config_path, backup_path)
                self.logger.info(f"💾 Backup created: {backup_path}")
        except:
            pass

        # Создаем новый конфиг
        self.create_default_config()

    def _process_wallets_config(self, wallets_config: List) -> List:
        """Обработка конфигурации кошельков"""
        if not isinstance(wallets_config, list):
            return []

        processed_wallets = []

        for wallet in wallets_config:
            if not isinstance(wallet, dict):
                continue

            processed_wallet = wallet.copy()

            # Обрабатываем приватный ключ
            private_key = processed_wallet.get('private_key') or processed_wallet.get('encrypted_private_key')
            if private_key:
                processed_wallet['private_key'] = private_key

            # Обрабатываем прокси (если есть)
            if 'proxy' in processed_wallet and processed_wallet['proxy']:
                proxy_config = processed_wallet['proxy']
                if isinstance(proxy_config, dict):
                    # Подставляем переменные окружения для прокси
                    if isinstance(proxy_config.get('ip'), str) and proxy_config['ip'].startswith('${'):
                        env_var = proxy_config['ip'][2:-1]
                        proxy_config['ip'] = os.getenv(env_var, proxy_config['ip'])

                    # Аналогично для других полей прокси
                    for field in ['port', 'username', 'password']:
                        if (isinstance(proxy_config.get(field), str) and
                                proxy_config[field].startswith('${')):
                            env_var = proxy_config[field][2:-1]
                            proxy_config[field] = os.getenv(env_var, proxy_config[field])
                else:
                    # Если proxy не dict, удаляем его
                    processed_wallet['proxy'] = None

            processed_wallets.append(processed_wallet)

        return processed_wallets

    def _process_networks_config(self, networks_config: List) -> List:
        """Обработка конфигурации сетей с подстановкой переменных окружения"""
        if not isinstance(networks_config, list):
            return []

        processed_networks = []

        for network in networks_config:
            if not isinstance(network, dict):
                continue

            processed_network = network.copy()

            # Подставляем переменные окружения в RPC URL
            rpc_url = processed_network.get('rpc_url', '')
            if isinstance(rpc_url, str) and rpc_url.startswith('${') and rpc_url.endswith('}'):
                env_var = rpc_url[2:-1]
                processed_network['rpc_url'] = os.getenv(env_var, rpc_url)

            processed_networks.append(processed_network)

        return processed_networks

    def validate_config(self):
        """Валидация конфигурации при загрузке"""
        issues = []

        # Проверка сетей
        for network in self.networks:
            if not network.get('rpc_url'):
                issues.append(f"Network {network.get('name')} missing RPC URL")
            if not network.get('chain_id'):
                issues.append(f"Network {network.get('name')} missing chain_id")

        # Проверка кошельков
        for wallet in self.wallets:
            if not wallet.get('name'):
                issues.append("Wallet missing name")
            if not wallet.get('private_key'):
                issues.append(f"Wallet {wallet.get('name')} missing private key")

        if issues:
            self.logger.warning(f"Config validation issues: {issues}")

        return len(issues) == 0

    def get_network_display_info(self, network_name: str) -> str:
        """Получить отображаемую информацию о сети"""
        network = self.get_network_by_name(network_name)
        if not network:
            return f"Unknown network: {network_name}"

        tokens_count = len(self.get_tokens_for_network(network_name))
        return (f"{network.get('name', 'Unknown')} "
                f"(ChainID: {network.get('chain_id', 'N/A')}, "
                f"Tokens: {tokens_count})")

    def update_network_tokens(self, network_name: str, tokens: dict):
        """Обновить токены для сети"""
        if network_name not in self.tokens_config:
            self.tokens_config[network_name] = {}

        self.tokens_config[network_name].update(tokens)
        self.save_config()
        self.logger.info(f"Updated tokens for {network_name}: {len(tokens)} tokens")

    def create_default_config(self):
        """Создание конфигурации по умолчанию с обновленной структурой"""
        self.logger.info("🔄 Creating default configuration...")

        # ✅ ОБНОВЛЕННАЯ СТРУКТУРА КОНФИГА
        self.config_data = {
            "wallets": [
                {
                    "name": "test",
                    "private_key": "YOUR_ENCRYPTED_PRIVATE_KEY_HERE",
                    "proxy": None
                }
            ],
            "networks": [
                {
                    "name": "Pharos Atlantic",
                    "rpc_url": "https://atlantic.dplabs-internal.com",
                    "wss_url": "wss://atlantic.dplabs-internal.com",
                    "explorer": "https://atlantic.pharosscan.xyz",
                    "chain_id": 688689,
                    "native_token": "PHRS",
                    "tokens": {
                        "PHRS": "0x0000000000000000000000000000000000000000",
                        "USDC": "0xE0BE08c77f415F577A1B3A9aD7a1Df1479564ec8",
                        "USDT": "0xE7E84B8B4f39C507499c40B4ac199B050e2882d5",
                        "WBTC": "0x0c64F03EEa5c30946D5c55B4b532D08ad74638a4",
                        "WETH": "0x7d211F77525ea39A0592794f793cC1036eEaccD5",
                        "WPHRS": "0x838800b758277CC111B2d48Ab01e5E164f8E9471"
                    },
                    "contracts": {
                        "faroswap_router": "0x1E656B2C6B6e91ef6E6A2B16475Df7b7D223e3c2",
                        "cashplus_subscription": "0x56f4add11d723412d27a9e9433315401b351d6e3"
                    }
                },
                {
                    "name": "Rise Testnet",
                    "rpc_url": "https://testnet.riselabs.xyz",
                    "wss_url": "wss://testnet.riselabs.xyz/ws",
                    "explorer": "https://explorer.testnet.riselabs.xyz",
                    "chain_id": 11155931,
                    "native_token": "ETH",
                    "tokens": {
                        "ETH": "0x0000000000000000000000000000000000000000",
                        "WETH": "0x4200000000000000000000000000000000000006",
                        "USDC": "0x8a93d247134d91e0de6f96547cb0204e5be8e5d8",
                        "USDT": "0x40918ba7f132e0acba2ce4de4c4baf9bd2d7d849",
                        "WBTC": "0xf32d39ff9f6aa7a7a64d7a4f00a54826ef791a55",
                        "RISE": "0xd6e1afe5ca8d00a2efc01b89997abe2de47fdfaf",
                        "CUSD": "0xA985e387dDF21b87c1Fe8A0025D827674040221E",
                        "MOG": "0x99dbe4aea58e518c50a1c04ae9b48c9f6354612f",
                        "PEPE": "0x6f6f570f45833e249e27022648a26f4076f48f78"
                    },
                    "contracts": {
                        "gaspump_router": "0x5eC9BEaCe4a0f46F77945D54511e2b454cb8F38E"
                    }
                }
            ],
            "operations": {
                "min_per_transaction": 1,
                "max_per_transaction": 2,
                "min_interval_minutes": 2,
                "max_interval_minutes": 5,
                "swap_percentage_min": 1.0,
                "swap_percentage_max": 5.0
            },
            "subscription_settings": {
                "min_usdt_balance": 0.1,
                "min_subscription_amount": 0.02,
                "max_subscription_amount": 0.2,
                "max_percentage_of_balance": 80,
                "max_transactions_per_wallet": 100,
                "retry_attempts": 2,
                "delay_between_wallets": 15
            }
        }

        # Сохраняем конфиг по умолчанию
        self.save_config()

    def save_config(self):
        """Сохранение конфигурации в файл"""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config_data, f, indent=2)
            self.logger.info(f"💾 Configuration saved to {self.config_path}")

            # Обновляем внутренние структуры
            self.wallets = self._safe_get(self.config_data, 'wallets', [])
            self.networks = self._safe_get(self.config_data, 'networks', [])
            self.operations_config = self._safe_get(self.config_data, 'operations', {})
            self.tokens_config = self._extract_tokens_from_networks()

        except Exception as e:
            self.logger.error(f"❌ Failed to save configuration: {e}")

    def _extract_tokens_from_networks(self) -> dict:
        """✅ ИЗВЛЕЧЕНИЕ ТОКЕНОВ ИЗ СТРУКТУРЫ СЕТЕЙ"""
        tokens_config = {}
        for network in self.networks:
            network_name = network.get('name')
            if network_name and 'tokens' in network:
                tokens_config[network_name] = network['tokens']
        return tokens_config

    def add_wallet(self, name: str, private_key: str, proxy_config: dict = None):
        """Добавление нового кошелька в конфиг"""
        from utils.security import encrypt_private_key

        wallet_data = {
            "name": name,
            "private_key": encrypt_private_key(private_key),
            "proxy": proxy_config
        }

        self.wallets.append(wallet_data)
        self.config_data['wallets'] = self.wallets
        self.save_config()
        self.logger.info(f"✅ Wallet {name} added successfully")

    def get_tokens_for_network(self, network_name: str) -> dict:
        """✅ ПОЛУЧЕНИЕ ТОКЕНОВ ДЛЯ СЕТИ (С ГИБКИМ ПОИСКОМ)"""
        network = self.get_network_by_name(network_name)
        return network.get('tokens', {}) if network else {}

        # Fallback: старая структура (отдельный tokens_config)
        return self.tokens_config.get(network_name, {})

    def get_token_address(self, network_name: str, token_symbol: str) -> str:
        """Получить адрес токена по символу"""
        tokens = self.get_tokens_for_network(network_name)
        return tokens.get(token_symbol)

    def get_contract_address(self, network_name: str, contract_name: str) -> str:
        """✅ ПОЛУЧЕНИЕ АДРЕСА КОНТРАКТА ДЛЯ СЕТИ"""
        for network in self.networks:
            if network.get('name') == network_name and 'contracts' in network:
                return network['contracts'].get(contract_name)
        return None

    def get_subscription_settings(self) -> dict:
        """✅ ПОЛУЧЕНИЕ НАСТРОЕК ДЛЯ ПОДПИСОК"""
        return self.config_data.get('subscription_settings', {
            'min_usdt_balance': 0.1,
            'min_subscription_amount': 0.02,
            'max_subscription_amount': 0.2,
            'max_percentage_of_balance': 80,
            'max_transactions_per_wallet': 100,
            'retry_attempts': 2,
            'delay_between_wallets': 15
        })

    def get_pharos_config(self) -> dict:
        """Получить конфигурацию сети Pharos"""
        return self.get_network_by_name('Pharos Atlantic')

    def get_pharos_tokens(self) -> dict:
        """Получить токены сети Pharos"""
        return self.get_tokens_for_network('Pharos Atlantic')

    def get_random_interval(self) -> int:
        """Получение случайного интервала"""
        min_interval = self.operations_config.get('min_interval_minutes', 2)
        max_interval = self.operations_config.get('max_interval_minutes', 5)
        return Randomizer.get_random_interval(min_interval, max_interval)

    def get_operations_count(self) -> int:
        """Получение количества операций за цикл"""
        min_ops = self.operations_config.get('min_per_transaction', 1)
        max_ops = self.operations_config.get('max_per_transaction', 2)
        return Randomizer.get_random_interval(min_ops, max_ops)

    def get_network_by_name(self, network_name: str) -> dict:
        """✅ ПОЛУЧЕНИЕ КОНФИГУРАЦИИ СЕТИ ПО ИМЕНИ (С ГИБКИМ ПОИСКОМ)"""
        network_name_lower = network_name.lower()

        for network in self.networks:
            # Сравниваем оба варианта - точное и нижний регистр
            if (network['name'].lower() == network_name_lower or
                    network['name'].lower().replace(' ', '') == network_name_lower.replace(' ', '')):
                return network

        # Если не нашли, пробуем частичное совпадение
        for network in self.networks:
            if (network_name_lower in network['name'].lower() or
                    network['name'].lower() in network_name_lower):
                return network

        return None

    def get_network_by_chain_id(self, chain_id: int) -> dict:
        """Получить конфигурацию сети по Chain ID"""
        for network in self.networks:
            if network['chain_id'] == chain_id:
                return network
        return None

    def get_all_networks(self) -> list:
        """Получить список всех сетей"""
        return self.networks.copy()

    def get_wallet_by_name(self, name: str) -> dict:
        """✅ ПОЛУЧЕНИЕ КОШЕЛЬКА ПО ИМЕНИ"""
        for wallet in self.wallets:
            if wallet.get('name') == name:
                return wallet
        return None