import os
import json
import time
import asyncio
from web3 import Web3
from eth_account import Account
from utils.security import decrypt_private_key, validate_private_key, encrypt_private_key
from core.proxy_manager import ProxyManager
from utils.input_utils import safe_getpass, secure_input, validate_ip_address, validate_port


class Wallet:
    def __init__(self, name: str, private_key: str, proxy_config: dict = None):
        # Сохраняем имя кошелька
        self.name = name

        # Дешифруем и валидируем приватный ключ
        decrypted_key = decrypt_private_key(private_key)
        if not validate_private_key(decrypted_key):
            raise ValueError("Invalid private key")

        self.account = Account.from_key(decrypted_key)
        self.address = self.account.address
        self.proxy_manager = ProxyManager(proxy_config) if proxy_config else None
        self.web3 = None
        self.balance_cache = {}
        self.cache_timeout = 300  # 5 минут

        # Устанавливаем логгер позже, когда он будет доступен
        self.logger = None

    def get_balance_cached(self, token_address: str = None, force_refresh: bool = False) -> int:
        """Получение баланса с кэшированием"""
        cache_key = token_address or 'native'
        current_time = time.time()

        if (not force_refresh and
                cache_key in self.balance_cache and
                current_time - self.balance_cache[cache_key]['timestamp'] < self.cache_timeout):
            return self.balance_cache[cache_key]['balance']

        balance = self.get_balance(token_address)
        self.balance_cache[cache_key] = {
            'balance': balance,
            'timestamp': current_time
        }
        return balance

    def set_logger(self, logger):
        """Установка логгера для кошелька и прокси менеджера"""
        self.logger = logger
        if self.proxy_manager:
            self.proxy_manager.set_logger(logger)

    def connect_to_network(self, rpc_url: str) -> bool:
        """Подключение к сети через прокси"""
        try:
            if self.proxy_manager:
                self.web3 = self.proxy_manager.create_web3_instance(rpc_url)
                if self.logger:
                    self.logger.info(f"🔌 Using proxy for wallet {self.name}")
            else:
                self.web3 = Web3(Web3.HTTPProvider(rpc_url))
                if self.logger:
                    self.logger.info(f"🔗 Direct connection for wallet {self.name}")

            is_connected = self.web3.is_connected()

            if is_connected and self.logger:
                # Показываем информацию о подключении
                chain_id = self.web3.eth.chain_id
                block_number = self.web3.eth.block_number
                self.logger.info(f"🌐 Wallet {self.name} connected to chain {chain_id}, block: {block_number}")

            return is_connected

        except Exception as e:
            if self.logger:
                self.logger.error(f"❌ Connection error for wallet {self.name}: {e}")
            return False

    def get_balance(self, token_address: str = None) -> int:
        """Получение баланса кошелька (нативного или токена)"""
        if not self.web3:
            return 0
        try:
            if token_address and token_address != "0x0000000000000000000000000000000000000000":
                # Баланс ERC20 токена
                erc20_abi = [
                    {
                        "constant": True,
                        "inputs": [{"name": "_owner", "type": "address"}],
                        "name": "balanceOf",
                        "outputs": [{"name": "balance", "type": "uint256"}],
                        "type": "function"
                    }
                ]
                token_contract = self.web3.eth.contract(
                    address=self.web3.to_checksum_address(token_address),
                    abi=erc20_abi
                )
                return token_contract.functions.balanceOf(self.address).call()
            else:
                # Нативный баланс (PHRS для Pharos)
                return self.web3.eth.get_balance(self.address)
        except Exception as e:
            if self.logger:
                self.logger.error(f"❌ Balance check failed for {self.name}: {e}")
            return 0

    def get_balance_readable(self, token_address: str = None, decimals: int = 18) -> float:
        """Получение баланса в читаемом формате"""
        balance = self.get_balance(token_address)
        return balance / (10 ** decimals) if balance > 0 else 0.0


class WalletManager:
    def __init__(self, config):
        self.config = config
        self.wallets = []
        self.logger = config.logger
        self.web3_instances = {}  # Кэш Web3 instances

    def _get_web3_for_network(self, network):
        """Получить или создать Web3 instance для сети"""
        if network['name'] in self.web3_instances:
            return self.web3_instances[network['name']]

        web3 = Web3(Web3.HTTPProvider(network['rpc_url']))
        self.web3_instances[network['name']] = web3
        return web3

    async def initialize_wallet_connections(self, specific_wallets=None):
        """Параллельная инициализация подключений кошельков с фильтрацией"""
        tasks = []

        # ✅ ФИЛЬТРУЕМ КОШЕЛЬКИ ЕСЛИ УКАЗАНЫ КОНКРЕТНЫЕ
        wallets_to_connect = self.wallets
        if specific_wallets:
            wallets_to_connect = [wallet for wallet in self.wallets if wallet.name in specific_wallets]
            self.logger.info(f"🔌 Connecting only selected wallets: {[w.name for w in wallets_to_connect]}")

        for wallet in wallets_to_connect:
            for network in self.config.networks:
                task = asyncio.create_task(self._connect_wallet_to_network(wallet, network))
                tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Анализ результатов
        successful_connections = sum(1 for r in results if r is True)
        self.logger.info(f"✅ {successful_connections}/{len(tasks)} wallet connections established")

    async def _connect_wallet_to_network(self, wallet, network):
        """Асинхронное подключение кошелька к сети"""
        try:
            # Используем asyncio.to_thread для синхронных операций Web3
            connected = await asyncio.to_thread(wallet.connect_to_network, network['rpc_url'])
            if connected:
                return True
        except Exception as e:
            self.logger.error(f"Connection failed for {wallet.name} to {network['name']}: {e}")
        return False

    async def check_balances_without_proxy(self, wallet_names=None, specific_network=None):
        """Проверка балансов кошельков без использования прокси (оптимизированно)"""
        if not self.config.networks:
            self.logger.error("❌ No networks configured")
            return

        # Фильтруем кошельки если указаны конкретные
        wallets_to_check = self.wallets
        if wallet_names:
            wallets_to_check = [wallet for wallet in self.wallets if wallet.name in wallet_names]

        if not wallets_to_check:
            self.logger.error("❌ No wallets available for balance check")
            return

        self.logger.info(f"🔍 Checking balances for {len(wallets_to_check)} wallets (without proxy)")

        # Создаем общий Web3 instance для сети (без прокси)
        networks_to_check = []
        if specific_network:
            network_config = self.config.get_network_by_name(specific_network)
            if network_config:
                networks_to_check = [network_config]
            else:
                self.logger.error(f"❌ Network '{specific_network}' not found")
                return
        else:
            networks_to_check = self.config.networks

        for network in networks_to_check:
            print(f"\n🌐 Network: {network['name']} ({network['native_token']})")
            print("-" * 40)

            try:
                # Создаем ОДИН Web3 instance для всей сети (без прокси)
                web3 = Web3(Web3.HTTPProvider(network['rpc_url']))

                if not web3.is_connected():
                    self.logger.error(f"❌ Failed to connect to {network['name']}")
                    continue

                for wallet in wallets_to_check:
                    try:
                        # Получаем баланс используя общий Web3 instance
                        balance = web3.eth.get_balance(wallet.address)
                        balance_readable = Web3.from_wei(balance, 'ether')

                        print(f"   {wallet.name}: {balance_readable:.6f} {network['native_token']}")

                        # Проверяем ERC20 токены для этой сети
                        await self._check_erc20_balances(web3, wallet, network)

                    except Exception as e:
                        print(f"   {wallet.name}: ❌ Error: {e}")

            except Exception as e:
                self.logger.error(f"❌ Error checking network {network['name']}: {e}")

    async def _check_erc20_balances(self, web3, wallet, network):
        """Проверка балансов ERC20 токенов (оптимизированно)"""
        try:
            tokens = self.config.get_tokens_for_network(network['name'])
            if not tokens:
                return

            # ABI для ERC20 токенов
            erc20_abi = [
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function"
                },
                {
                    "constant": True,
                    "inputs": [],
                    "name": "decimals",
                    "outputs": [{"name": "", "type": "uint8"}],
                    "type": "function"
                },
                {
                    "constant": True,
                    "inputs": [],
                    "name": "symbol",
                    "outputs": [{"name": "", "type": "string"}],
                    "type": "function"
                }
            ]

            # Проверяем только ненулевые балансы
            for token_symbol, token_address in tokens.items():
                if token_address == "0x0000000000000000000000000000000000000000":
                    continue  # Пропускаем нативный токен

                try:
                    token_contract = web3.eth.contract(
                        address=web3.to_checksum_address(token_address),
                        abi=erc20_abi
                    )

                    balance = token_contract.functions.balanceOf(wallet.address).call()

                    if balance > 0:
                        try:
                            decimals = token_contract.functions.decimals().call()
                        except:
                            decimals = 18

                        balance_formatted = balance / (10 ** decimals)
                        print(f"        {token_symbol}: {balance_formatted:.6f}")

                except Exception as e:
                    # Пропускаем ошибки для отдельных токенов
                    continue

        except Exception as e:
            # Игнорируем общие ошибки проверки токенов
            pass

    async def load_wallets(self, connect_to_networks=False):
        """Загрузка кошельков из конфигурации с опциональным подключением к сетям"""
        if not self.config.wallets:
            self.logger.warning("⚠️ No wallets configured")
            return

        for wallet_config in self.config.wallets:
            try:
                wallet = Wallet(
                    name=wallet_config.get('name', f'wallet_{len(self.wallets) + 1}'),
                    private_key=wallet_config['private_key'],
                    proxy_config=wallet_config.get('proxy')
                )

                # Устанавливаем логгер для кошелька
                wallet.set_logger(self.logger)

                # ✅ ПОДКЛЮЧАЕМ К СЕТИ ТОЛЬКО ЕСЛИ ЯВНО УКАЗАНО
                if connect_to_networks:
                    connected = False
                    for network in self.config.networks:
                        if wallet.connect_to_network(network['rpc_url']):
                            # ПРОВЕРЯЕМ РЕАЛЬНЫЙ БАЛАНС после подключения
                            balance = wallet.get_balance()
                            balance_readable = Web3.from_wei(balance, 'ether') if balance > 0 else 0
                            native_token = network.get('native_token', 'ETH')

                            self.logger.info(
                                f"✅ Wallet {wallet.name} connected to {network['name']}, balance: {balance_readable:.6f} {native_token}")
                            connected = True
                            break

                    if not connected:
                        self.logger.warning(f"⚠️ Wallet {wallet.name} failed to connect to any network")
                else:
                    # ✅ ТОЛЬКО ЛОГИРУЕМ ИНФОРМАЦИЮ О ПРОКСИ БЕЗ ПОДКЛЮЧЕНИЯ
                    if wallet.proxy_manager:
                        proxy_ip = wallet.proxy_manager.proxy_config.get('ip', 'unknown')
                        self.logger.info(f"🔌 Wallet {wallet.name} has proxy: {proxy_ip}")
                    else:
                        self.logger.info(f"🔗 Wallet {wallet.name} - direct connection")

                self.wallets.append(wallet)

            except Exception as e:
                self.logger.error(f"❌ Failed to load wallet {wallet_config.get('name', 'unknown')}: {e}")

    def get_wallet_by_address(self, address: str):
        """Получить кошелек по адресу"""
        for wallet in self.wallets:
            if wallet.address.lower() == address.lower():
                return wallet
        return None

    async def test_wallet_connections(self):
        """Тестирование подключения кошельков с их прокси (для отладки)"""
        if not self.wallets:
            self.logger.warning("⚠️ No wallets loaded")
            return

        self.logger.info("🔧 Testing wallet connections with their proxies...")

        for wallet in self.wallets:
            for network in self.config.networks:
                try:
                    connected = wallet.connect_to_network(network['rpc_url'])
                    status = "✅" if connected else "❌"
                    proxy_info = "with proxy" if wallet.proxy_manager else "direct"
                    self.logger.info(f"   {status} {wallet.name} to {network['name']} ({proxy_info})")

                    if connected:
                        break

                except Exception as e:
                    self.logger.error(f"   ❌ {wallet.name} connection test failed: {e}")

    def get_wallet_by_name(self, name: str):
        """Получить кошелек по имени"""
        for wallet in self.wallets:
            if wallet.name == name:
                return wallet
        return None

    def get_random_wallet(self):
        """Получить случайный кошелек"""
        import random
        return random.choice(self.wallets) if self.wallets else None

    def get_wallets_count(self) -> int:
        """Получить количество загруженных кошельков"""
        return len(self.wallets)

    def get_wallet_names(self):
        """Получить список имен кошельков"""
        return [wallet.name for wallet in self.wallets]

    @staticmethod
    def add_wallet_interactive():
        """Интерактивное добавление кошелька"""
        from utils.security import encrypt_private_key, validate_private_key

        print("\n🎒 Добавление нового кошелька")
        print("=" * 40)

        # Загружаем текущий конфиг
        try:
            with open('config/config.json', 'r') as f:
                config = json.load(f)
        except Exception as e:
            print(f"❌ Ошибка загрузки конфига: {e}")
            return False

        existing_wallets = config.get('wallets', [])

        # Имя кошелька
        existing_names = [w.get('name', '') for w in existing_wallets]
        next_number = 1
        for wallet in existing_wallets:
            name = wallet.get('name', '')
            if name.startswith('wallet_'):
                try:
                    num = int(name[7:])
                    if num >= next_number:
                        next_number = num + 1
                except ValueError:
                    pass

        wallet_name = f"wallet_{next_number}"
        custom_name = secure_input(f"Имя кошелька [по умолчанию: {wallet_name}]")
        if custom_name:
            if custom_name in existing_names:
                print("❌ Кошелек с таким именем уже существует")
                return False
            wallet_name = custom_name

        # Приватный ключ
        print("\n🔑 Ввод приватного ключа:")
        print("⚠️  Приватный ключ будет зашифрован и безопасно сохранен")

        while True:
            private_key = safe_getpass("Введите приватный ключ")

            if not private_key:
                print("❌ Приватный ключ не может быть пустым")
                continue

            if validate_private_key(private_key):
                break
            else:
                print("❌ Невалидный приватный ключ. Попробуйте еще раз.")

        # Прокси
        print("\n🔌 Настройки прокси:")
        use_proxy = secure_input("Использовать прокси? (y/N)").strip().lower()

        proxy_config = None
        if use_proxy == 'y':
            print("\n📡 Введите данные прокси:")

            # IP адрес
            while True:
                ip = secure_input("IP адрес прокси")
                if validate_ip_address(ip):
                    break
                else:
                    print("❌ Невалидный IP адрес. Пример: 192.168.1.1")

            # Порт
            while True:
                port = secure_input("Порт прокси")
                if validate_port(port):
                    break
                else:
                    print("❌ Невалидный порт. Должен быть от 1 до 65535")

            # Логин и пароль (опционально)
            username = secure_input("Логин прокси (опционально, Enter чтобы пропустить)")
            password = ""
            if username:
                password = safe_getpass("Пароль прокси")

            proxy_config = {
                "ip": ip,
                "port": port
            }

            if username:
                proxy_config["username"] = username
            if password:
                proxy_config["password"] = password

        # Подтверждение
        print("\n📋 Подтверждение данных:")
        print(f"   Имя: {wallet_name}")
        print(f"   Прокси: {'Да' if proxy_config else 'Нет'}")

        confirm = secure_input("\nДобавить кошелек? (y/N)").strip().lower()
        if confirm != 'y':
            print("❌ Отменено пользователем")
            return False

        # Шифруем и сохраняем
        try:
            encrypted_key = encrypt_private_key(private_key)

            new_wallet = {
                "name": wallet_name,
                "private_key": encrypted_key,
                "proxy": proxy_config
            }

            existing_wallets.append(new_wallet)
            config['wallets'] = existing_wallets

            with open('config/config.json', 'w') as f:
                json.dump(config, f, indent=2)

            account = Account.from_key(private_key)

            print(f"\n✅ Кошелек успешно добавлен!")
            print(f"   Имя: {wallet_name}")
            print(f"   Адрес: {account.address}")
            print(f"   Прокси: {'Да' if proxy_config else 'Нет'}")

            return True

        except Exception as e:
            print(f"❌ Ошибка сохранения: {e}")
            return False

    @staticmethod
    def show_wallet_info():
        """Показать информацию о кошельках"""
        from utils.security import decrypt_private_key

        try:
            with open('config/config.json', 'r') as f:
                config = json.load(f)

            wallets = config.get('wallets', [])

            print("\n📋 Существующие кошельки:")
            print("=" * 50)

            if not wallets:
                print("❌ Кошельков нет")
                return

            for i, wallet in enumerate(wallets, 1):
                print(f"{i}. {wallet.get('name', 'unnamed')}")

                # Показываем адрес кошелька
                try:
                    private_key = decrypt_private_key(wallet.get('private_key', ''))
                    account = Account.from_key(private_key)
                    print(f"   📬 Адрес: {account.address}")
                except:
                    print(f"   📬 Адрес: (не удалось расшифровать)")

                if wallet.get('proxy'):
                    proxy = wallet['proxy']
                    print(f"   🔌 Прокси: {proxy.get('ip')}:{proxy.get('port')}")
                    if proxy.get('username'):
                        print(f"   👤 Логин: {proxy.get('username')}")
                else:
                    print(f"   🔌 Прокси: Нет")
                print()

        except Exception as e:
            print(f"❌ Ошибка загрузки кошельков: {e}")

    @staticmethod
    def get_wallet_names_from_config():
        """Получить список имен кошельков из конфига"""
        try:
            with open('config/config.json', 'r') as f:
                config = json.load(f)
            return [wallet.get('name', 'unnamed') for wallet in config.get('wallets', [])]
        except:
            return []

    @staticmethod
    def select_wallets_interactive():
        """✅ ИСПРАВЛЕННЫЙ ИНТЕРАКТИВНЫЙ ВЫБОР КОШЕЛЬКОВ"""
        try:
            with open('config/config.json', 'r') as f:
                config = json.load(f)

            wallets = config.get('wallets', [])

            if not wallets:
                print("❌ Кошельков нет. Сначала добавьте кошельки.")
                return None

            print("\n🎒 Выберите кошельки для работы:")
            print("=" * 40)

            # Показываем все кошельки
            for i, wallet in enumerate(wallets, 1):
                proxy_status = "🔌 с прокси" if wallet.get('proxy') else "🔗 прямой доступ"
                print(f"{i}. {wallet.get('name', 'unnamed')} - {proxy_status}")

            print(f"{len(wallets) + 1}. 🚀 Все кошельки")
            print(f"{len(wallets) + 2}. ↩️ Назад")

            try:
                choice = secure_input(
                    f"\nВыберите кошельки (через запятую, 'all' для всех или номер {len(wallets) + 1}): ").strip()

                if choice.lower() == 'all' or choice == str(len(wallets) + 1):
                    # ✅ ВЫБРАНЫ ВСЕ КОШЕЛЬКИ
                    selected_names = [wallet['name'] for wallet in wallets]
                    print(f"✅ Выбраны все кошельки: {', '.join(selected_names)}")
                    return selected_names

                elif choice == str(len(wallets) + 2) or choice == '0':
                    # Назад
                    return None

                elif ',' in choice:
                    # ✅ ВЫБРАНО НЕСКОЛЬКО КОШЕЛЬКОВ ЧЕРЕЗ ЗАПЯТУЮ
                    choices = [c.strip() for c in choice.split(',')]
                    selected_names = []

                    for choice_str in choices:
                        if choice_str.isdigit():
                            choice_num = int(choice_str)
                            if 1 <= choice_num <= len(wallets):
                                selected_names.append(wallets[choice_num - 1]['name'])
                            else:
                                print(f"❌ Неверный номер: {choice_str}")
                                return None
                        else:
                            # Поиск по имени
                            wallet_found = False
                            for wallet in wallets:
                                if wallet['name'].lower() == choice_str.lower():
                                    selected_names.append(wallet['name'])
                                    wallet_found = True
                                    break
                            if not wallet_found:
                                print(f"❌ Кошелек не найден: {choice_str}")
                                return None

                    if selected_names:
                        print(f"✅ Выбраны кошельки: {', '.join(selected_names)}")
                        return selected_names
                    else:
                        print("❌ Не выбрано ни одного кошелька")
                        return None

                elif choice.isdigit():
                    # ✅ ВЫБРАН ОДИН КОШЕЛЕК ПО НОМЕРУ
                    choice_num = int(choice)
                    if 1 <= choice_num <= len(wallets):
                        selected_name = wallets[choice_num - 1]['name']
                        print(f"✅ Выбран кошелек: {selected_name}")
                        return [selected_name]
                    else:
                        print("❌ Неверный номер кошелька")
                        return None

                else:
                    # ✅ ПОИСК ПО ИМЕНИ
                    for wallet in wallets:
                        if wallet['name'].lower() == choice.lower():
                            print(f"✅ Выбран кошелек: {wallet['name']}")
                            return [wallet['name']]

                    print("❌ Кошелек не найден")
                    return None

            except Exception as e:
                print(f"❌ Ошибка выбора кошельков: {e}")
                return None

        except Exception as e:
            print(f"❌ Ошибка загрузки кошельков: {e}")
            return None