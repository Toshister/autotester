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
                self.logger.debug(
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
                    "PCT": "0x4f848d61b35033619ce558a2fce8447cedd38d0d",
                    "CORP": "0x656b4948c470f3420805abcb43f3928820a0f26d",
                    "UST": "0x5e789bb07b2225132d26bb0ffaca7e37a5ecbebb",
                    "WBTC": "0x0c64F03EEa5c30946D5c55B4b532D08ad74638a4",
                    "WETH": "0x7d211F77525ea39A0592794f793cC1036eEaccD5",
                    "WPHRS": "0x838800b758277CC111B2d48Ab01e5E164f8E9471"
                },
                "contracts": {
                    "bitverse_router": "0x585fC3b498b1ABA1F0527663789361D3547aFC88",
                    "structure_subscription": "0x62fdbc600e8badf8127e6298dd12b961edf08b5f"
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
                },
                {
                    "name": "OPN Testnet",
                    "rpc_url": "https://testnet-rpc.iopn.tech",
                    "explorer": "https://testnet.iopn.tech",
                    "chain_id": 984,
                    "native_token": "OPN",
                    "tokens": {
                        "OPN": "0x0000000000000000000000000000000000000000",
                        "USDC": "0x3600000000000000000000000000000000000000",
                        "EURC": "0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a",
                        "tBNB": "0x92cF36713a5622351c9489D5556B90B321873607",
                        "WOPN": "0xBc022C9dEb5AF250A526321d16Ef52E39b4DBD84",
                        "tUSDT": "0x3e01b4d892E0D0A219eF8BBe7e260a6bc8d9B31b",
                        "OPNT": "0x2aEc1Db9197Ff284011A6A1d0752AD03F5782B0d"
                    },
                    "contracts": {
                        "iopn_router": "0xb489bce5c9c9364da2d1d1bc5ce4274f63141885"
                    }
                },
                {
                    "name": "Arc Testnet",
                    "rpc_url": "https://rpc.testnet.arc.network",
                    "wss_url": "wss://rpc.testnet.arc.network",
                    "explorer": "https://testnet.arcscan.app",
                    "chain_id": 5042002,
                    "native_token": "USDC",
                    "tokens": {
                        "USDC": "0x3600000000000000000000000000000000000000",
                        "EURC": "0x89B50855Aa3bE2F677cD6303Cec089B5F319D72a",
                        "WUSDC": "0x911b4000D3422F482F4062a913885f7b035382Df",
                        "dUSDT": "0x1Bcabc3f981D4E4F7CB65fdcBc112139d670EfB7",
                        "BRID": "0x18635Cc718b2a1f6A62f7c2C7008cF0607eea8d9",
                        "bbToken": "0x28951a0909Be0ae9Afb53015509C1732fd027ef3",
                        "CA4F": "0xBc4e50dEBe49a207cf977b220416b6a5e289d2b5",
                        "rUSDC": "0xAAC9c6387FFd1F840dA9F4E0F69E9838d4cB6Be0",
                        "TST": "0xb2B6dA55472A9077B45Bd9CC57C42E107c56f18e",
                        "wARC": "0x7D94bB687216f36Df9Deac7B340E470F06473B25",
                        "SYN": "0xc5124c846c6e6307986988dfb7e743327aa05f19",
                        "USDT": "0x175cdb1d338945f0d851a741ccf787d343e57952"
                    },
                    "contracts": {
                        "curve_router": "0xff5cb29241f002ffed2eaa224e3e996d24a6e8d1",
                        "universal_router": "0xbf4479C07Dc6fdc6dAa764A0ccA06969e894275F",
                        "permit2": "0x000000000022d473030f116ddee9f6b43ac78ba3"
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
                "contract_address": "0x62fdbc600e8badf8127e6298dd12b961edf08b5f",
                "max_percentage_of_balance": 90,
                "retry_attempts": 2,
                "delay_between_wallets": 15,
                "min_native_balance": 0.001,
                "approve_gas_limit": 120000,
                "subscribe_gas_limit": 450000,
                "assets": [
                    {
                        "name": "Private Credit",
                        "symbol": "PCT",
                        "token_address": "0x4f848d61b35033619ce558a2fce8447cedd38d0d",
                        "asset_id": "0x8b79ddf5ff2f0db54884b06a0b748a687abe7eb723e676eac22a5a811e9312ae",
                        "decimals": 18,
                        "min_amount": 35.0,
                        "max_amount": 66.0
                    },
                    {
                        "name": "Corporate Bond",
                        "symbol": "CORP",
                        "token_address": "0x656b4948c470f3420805abcb43f3928820a0f26d",
                        "asset_id": "0xb6dad7cac45cd7ee7d611c0160667e8595bcece1e8dc2b22228b6f329e1caa60",
                        "decimals": 18,
                        "min_amount": 35.0,
                        "max_amount": 66.0
                    },
                    {
                        "name": "US Treasury",
                        "symbol": "UST",
                        "token_address": "0x5e789bb07b2225132d26bb0ffaca7e37a5ecbebb",
                        "asset_id": "0xd048a586b49e0cf14afc137d0ebec0024a50aa5be56d006ecf46088f47537e33",
                        "decimals": 18,
                        "min_amount": 35.0,
                        "max_amount": 66.0
                    }
                ]
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
            'contract_address': '',
            'max_percentage_of_balance': 90,
            'retry_attempts': 2,
            'delay_between_wallets': 15,
            'min_native_balance': 0.001,
            'approve_gas_limit': 120000,
            'subscribe_gas_limit': 450000,
            'assets': []
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
        interval_seconds = Randomizer.get_random_interval(min_interval, max_interval) * 60
        # Ограничиваем верхний предел 25 сек при расчёте интервалов
        return min(interval_seconds, 25)

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
