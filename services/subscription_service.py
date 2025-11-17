import asyncio
import random
from web3 import Web3
from utils.logger import setup_logger
from config.constants import is_pharos_network, normalize_network_name
from utils.randomizer import Randomizer


class SubscriptionService:
    def __init__(self, web3_instance, config, gas_monitor=None):
        self.web3 = web3_instance
        self.config = config
        self.gas_monitor = gas_monitor
        self.logger = setup_logger("SubscriptionService")

        # ✅ Адреса контрактов для CashPlus Atlantic
        self.usdt_address = "0xE7E84B8B4f39C507499c40B4ac199B050e2882d5"  # USDT на Pharos
        self.cashplus_contract_address = "0x56f4add11d723412d27a9e9433315401b351d6e3"  # CashPlus Atlantic

        # ABI для контрактов
        self.usdt_abi = self._get_usdt_abi()
        self.cashplus_abi = self._get_cashplus_abi()

        # ✅ ТРЕКИНГ ТРАНЗАКЦИЙ ДЛЯ КОШЕЛЬКОВ
        self.wallet_transaction_count = {}

    def _get_usdt_abi(self):
        """ABI для USDT токена"""
        return [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function"
            },
            {
                "constant": False,
                "inputs": [
                    {"name": "_spender", "type": "address"},
                    {"name": "_value", "type": "uint256"}
                ],
                "name": "approve",
                "outputs": [{"name": "success", "type": "bool"}],
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
            },
            {
                "constant": True,
                "inputs": [
                    {"name": "_owner", "type": "address"},
                    {"name": "_spender", "type": "address"}
                ],
                "name": "allowance",
                "outputs": [{"name": "", "type": "uint256"}],
                "type": "function"
            }
        ]

    def _get_cashplus_abi(self):
        """ABI для CashPlus Atlantic контракта"""
        return [
            {
                "inputs": [
                    {"internalType": "address", "name": "uAddress", "type": "address"},
                    {"internalType": "uint256", "name": "uAmount", "type": "uint256"}
                ],
                "name": "subscribe",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "address", "name": "uAddress", "type": "address"}
                ],
                "name": "unsubscribe",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "address", "name": "user", "type": "address"},
                    {"internalType": "address", "name": "token", "type": "address"}
                ],
                "name": "getUserSubscription",
                "outputs": [
                    {"internalType": "uint256", "name": "amount", "type": "uint256"},
                    {"internalType": "uint256", "name": "startTime", "type": "uint256"}
                ],
                "stateMutability": "view",
                "type": "function"
            }
        ]

    async def get_wallet_transaction_count(self, wallet_address: str) -> int:
        """✅ ПОЛУЧЕНИЕ КОЛИЧЕСТВА ТРАНЗАКЦИЙ КОШЕЛЬКА"""
        try:
            # Используем web3 для получения nonce (количество отправленных транзакций)
            transaction_count = self.web3.eth.get_transaction_count(wallet_address)

            # Также проверяем наш внутренний счетчик
            internal_count = self.wallet_transaction_count.get(wallet_address.lower(), 0)

            # Используем максимум из двух значений
            total_count = max(transaction_count, internal_count)

            self.logger.info(f"📊 Wallet {wallet_address[:8]}... transaction count: {total_count}")
            return total_count

        except Exception as e:
            self.logger.error(f"❌ Error getting transaction count for {wallet_address[:8]}...: {e}")
            return self.wallet_transaction_count.get(wallet_address.lower(), 0)

    def _increment_wallet_transaction_count(self, wallet_address: str):
        """✅ УВЕЛИЧЕНИЕ СЧЕТЧИКА ТРАНЗАКЦИЙ ДЛЯ КОШЕЛЬКА"""
        wallet_key = wallet_address.lower()
        current_count = self.wallet_transaction_count.get(wallet_key, 0)
        self.wallet_transaction_count[wallet_key] = current_count + 1
        self.logger.info(f"📈 Updated transaction count for {wallet_address[:8]}...: {current_count + 1}")

    async def check_transaction_limit(self, wallet, max_transactions: int = 100) -> bool:
        """✅ ПРОВЕРКА ЛИМИТА ТРАНЗАКЦИЙ ДЛЯ КОШЕЛЬКА"""
        try:
            transaction_count = await self.get_wallet_transaction_count(wallet.address)

            if transaction_count >= max_transactions:
                self.logger.warning(
                    f"⏭️ Skipping {wallet.name} - transaction limit reached: {transaction_count}/{max_transactions}")
                return False
            else:
                self.logger.info(f"✅ {wallet.name} transaction count: {transaction_count}/{max_transactions}")
                return True

        except Exception as e:
            self.logger.error(f"❌ Error checking transaction limit for {wallet.name}: {e}")
            return True  # Разрешаем если ошибка проверки

    async def get_usdt_balance(self, wallet) -> float:
        """Получение баланса USDT в долларах с правильными decimals"""
        try:
            usdt_contract = self.web3.eth.contract(
                address=Web3.to_checksum_address(self.usdt_address),
                abi=self.usdt_abi
            )

            balance_wei = usdt_contract.functions.balanceOf(wallet.address).call()
            decimals = usdt_contract.functions.decimals().call()

            # ✅ USDT обычно имеет 6 decimals, но проверим
            balance_usd = balance_wei / (10 ** decimals)

            # Получаем символ токена для логирования
            try:
                symbol = usdt_contract.functions.symbol().call()
            except:
                symbol = "USDT"

            self.logger.info(f"💰 {wallet.name} {symbol} баланс: {balance_usd:.4f} {symbol} (decimals: {decimals})")
            return balance_usd

        except Exception as e:
            self.logger.error(f"❌ Ошибка получения баланса USDT для {wallet.name}: {e}")
            return 0.0

    async def get_native_balance(self, wallet) -> float:
        """Получение баланса нативного токена (PHRS) с использованием конфига"""
        try:
            balance_wei = self.web3.eth.get_balance(wallet.address)
            balance_native = self.web3.from_wei(balance_wei, 'ether')

            # ✅ ПОЛУЧАЕМ ИНФОРМАЦИЮ ИЗ КОНФИГА
            normalized_network = normalize_network_name('Pharos Atlantic')
            network_config = self.config.get_network_by_name(normalized_network)

            if network_config:
                native_token = network_config.get('native_token', 'PHRS')
                self.logger.info(f"💰 {wallet.name} {native_token} баланс: {balance_native:.6f} {native_token}")
            else:
                self.logger.info(f"💰 {wallet.name} native баланс: {balance_native:.6f} PHRS")

            return float(balance_native)

        except Exception as e:
            self.logger.error(f"❌ Ошибка получения нативного баланса для {wallet.name}: {e}")
            return 0.0

    async def check_allowance(self, wallet, spender: str) -> int:
        """Проверка allowance для USDT"""
        try:
            usdt_contract = self.web3.eth.contract(
                address=Web3.to_checksum_address(self.usdt_address),
                abi=self.usdt_abi
            )

            allowance = usdt_contract.functions.allowance(
                wallet.address,
                Web3.to_checksum_address(spender)
            ).call()

            return allowance

        except Exception as e:
            self.logger.error(f"❌ Ошибка проверки allowance для {wallet.name}: {e}")
            return 0

    async def approve_usdt(self, wallet, spender: str, amount: int) -> bool:
        """Approve USDT для CashPlus контракта"""
        try:
            usdt_contract = self.web3.eth.contract(
                address=Web3.to_checksum_address(self.usdt_address),
                abi=self.usdt_abi
            )

            nonce = self.web3.eth.get_transaction_count(wallet.address)

            transaction = usdt_contract.functions.approve(
                Web3.to_checksum_address(spender),
                amount
            ).build_transaction({
                'from': wallet.address,
                'gas': 100000,
                'gasPrice': self.web3.eth.gas_price,
                'nonce': nonce,
                'chainId': self.web3.eth.chain_id
            })

            signed_txn = wallet.account.sign_transaction(transaction)
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.raw_transaction)

            self.logger.info(f"📝 Approval transaction sent for {wallet.name}: {tx_hash.hex()}")

            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt.status == 1:
                # ✅ УВЕЛИЧИВАЕМ СЧЕТЧИК ТРАНЗАКЦИЙ ПРИ УСПЕШНОМ APPROVE
                self._increment_wallet_transaction_count(wallet.address)

            return receipt.status == 1

        except Exception as e:
            self.logger.error(f"❌ Approval failed for {wallet.name}: {e}")
            return False

    async def execute_subscribe(self, wallet, amount_usd: float) -> bool:
        """Выполнение подписки на указанную сумму"""
        try:
            # Получаем контракт CashPlus
            cashplus_contract = self.web3.eth.contract(
                address=Web3.to_checksum_address(self.cashplus_contract_address),
                abi=self.cashplus_abi
            )

            # Конвертируем USD в USDT (предполагаем 1:1)
            usdt_contract = self.web3.eth.contract(
                address=Web3.to_checksum_address(self.usdt_address),
                abi=self.usdt_abi
            )

            decimals = usdt_contract.functions.decimals().call()
            amount_wei = int(amount_usd * (10 ** decimals))

            self.logger.info(f"🎯 {wallet.name} subscribing: {amount_usd:.4f}$ ({amount_wei} wei)")

            # Проверяем и делаем approve если нужно
            allowance = await self.check_allowance(wallet, self.cashplus_contract_address)
            if allowance < amount_wei:
                self.logger.info(f"🔓 Approving USDT for {wallet.name}...")
                if not await self.approve_usdt(wallet, self.cashplus_contract_address, amount_wei):
                    self.logger.error(f"❌ Failed to approve USDT for {wallet.name}")
                    return False

            # Выполняем подписку
            nonce = self.web3.eth.get_transaction_count(wallet.address)

            transaction = cashplus_contract.functions.subscribe(
                Web3.to_checksum_address(self.usdt_address),  # uAddress
                amount_wei  # uAmount
            ).build_transaction({
                'from': wallet.address,
                'gas': 200000,
                'gasPrice': self.web3.eth.gas_price,
                'nonce': nonce,
                'chainId': self.web3.eth.chain_id
            })

            signed_txn = wallet.account.sign_transaction(transaction)
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.raw_transaction)

            self.logger.info(f"📤 Subscribe transaction sent for {wallet.name}: {tx_hash.hex()}")

            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt.status == 1:
                self.logger.info(f"✅ {wallet.name} subscribe successful! TX: {tx_hash.hex()}")

                # ✅ УВЕЛИЧИВАЕМ СЧЕТЧИК ТРАНЗАКЦИЙ ПРИ УСПЕШНОЙ ПОДПИСКЕ
                self._increment_wallet_transaction_count(wallet.address)

                # ✅ ИСПОЛЬЗУЕМ НОРМАЛИЗОВАННОЕ ИМЯ СЕТИ ДЛЯ EXPLORER
                normalized_network = normalize_network_name('Pharos Atlantic')
                network_config = self.config.get_network_by_name(normalized_network)
                if network_config and network_config.get('explorer'):
                    explorer_url = network_config['explorer'].rstrip('/')
                    tx_explorer_url = f"{explorer_url}/tx/{tx_hash.hex()}"
                    self.logger.info(f"🌐 View in explorer: {tx_explorer_url}")

                return True
            else:
                self.logger.error(f"❌ {wallet.name} subscribe failed: {tx_hash.hex()}")
                return False

        except Exception as e:
            self.logger.error(f"❌ Subscribe execution failed for {wallet.name}: {e}")
            return False

    def _round_to_four_decimals(self, amount: float) -> float:
        """Округление до 4 знаков после запятой"""
        return round(amount, 4)

    async def execute_random_subscription(self, wallet, network_name: str) -> bool:
        """✅ ИСПРАВЛЕННАЯ ВЕРСИЯ С ПРАВИЛЬНЫМ ЛОГИРОВАНИЕМ БАЛАНСОВ"""
        try:
            # ✅ ИСПОЛЬЗУЕМ УНИФИЦИРОВАННУЮ ПРОВЕРКУ СЕТИ
            if not is_pharos_network(network_name):
                self.logger.info(f"⚠️ Subscription only available for Pharos Atlantic network")
                return False

            self.logger.info(f"🎯 Starting subscription check for {wallet.name}")

            # ✅ 1. ПОКАЗЫВАЕМ ОБА БАЛАНСА: НАТИВНЫЙ И USDT
            native_balance = await self.get_native_balance(wallet)
            usdt_balance = await self.get_usdt_balance(wallet)

            self.logger.info(f"📊 {wallet.name} balances - Native: {native_balance:.6f} PHRS, USDT: {usdt_balance:.4f}$")

            # ✅ 2. ПРОВЕРКА ЛИМИТА ТРАНЗАКЦИЙ (100 макс)
            max_transactions = self.config.get_subscription_settings().get('max_transactions_per_wallet', 100)
            if not await self.check_transaction_limit(wallet, max_transactions):
                return False

            # ✅ 3. ПРОВЕРКА ПОДКЛЮЧЕНИЯ К СЕТИ
            if not self.web3.is_connected():
                self.logger.error("❌ Web3 not connected")
                return False

            # ✅ 4. ПРОВЕРКА БАЛАНСА USDT (для подписки)
            min_usdt_balance = self.config.get_subscription_settings().get('min_usdt_balance', 0.1)
            if usdt_balance < min_usdt_balance:
                self.logger.info(
                    f"⏭️ Skipping {wallet.name} - low USDT: {usdt_balance:.4f}$ (min: {min_usdt_balance}$)")
                return False

            # ✅ 5. ГЕНЕРАЦИЯ СУММЫ С УЧЕТОМ БАЛАНСА USDT И НАСТРОЕК
            subscription_settings = self.config.get_subscription_settings()
            min_amount = subscription_settings.get('min_subscription_amount', 0.02)
            max_amount = subscription_settings.get('max_subscription_amount', 0.2)
            max_percentage = subscription_settings.get('max_percentage_of_balance', 80) / 100

            # Ограничиваем максимальную сумму процентом от USDT баланса
            max_possible = min(max_amount, usdt_balance * max_percentage)

            if min_amount > max_possible:
                self.logger.info(f"⏭️ Skipping {wallet.name} - USDT balance too low for min subscription")
                return False

            subscription_amount = random.uniform(min_amount, max_possible)
            subscription_amount = self._round_to_four_decimals(subscription_amount)

            self.logger.info(
                f"💸 {wallet.name} subscription: {subscription_amount:.4f}$ USDT (balance: {usdt_balance:.4f}$ USDT)")

            # ✅ 6. ВЫПОЛНЕНИЕ ПОДПИСКИ
            return await self.execute_subscribe(wallet, subscription_amount)

        except Exception as e:
            self.logger.error(f"❌ Subscription failed for {wallet.name}: {e}")
            return False

    def get_wallet_stats(self) -> dict:
        """✅ ПОЛУЧЕНИЕ СТАТИСТИКИ ПО ТРАНЗАКЦИЯМ КОШЕЛЬКОВ"""
        return self.wallet_transaction_count.copy()