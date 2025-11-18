import asyncio
import random
from web3 import Web3
from utils.logger import setup_logger
from utils.randomizer import Randomizer
from config.constants import is_rise_network, is_opn_network, normalize_network_name


class SwapService:
    def __init__(self, web3_instance, config, gas_monitor=None):
        self.web3 = web3_instance
        self.config = config
        self.gas_monitor = gas_monitor
        self.logger = setup_logger(__name__)

        # ✅ ABI
        self.erc20_abi = self._get_erc20_abi()
        self.router_abi = None

        # ✅ ИНИЦИАЛИЗАЦИЯ РОУТЕРА
        self.router_address = None
        self.router_contract = None
        self.router_type = None

        self._initialize_router()

    def _initialize_router(self):
        """Инициализация роутера"""
        try:
            if not self.web3 or not self.web3.is_connected():
                self.logger.error("❌ Web3 not connected")
                return

            chain_id = self.web3.eth.chain_id
            network_config = self.config.get_network_by_chain_id(chain_id)
            network_name = network_config['name'] if network_config else ""
            normalized_name = normalize_network_name(network_name)

            self.logger.info(f"🔍 Initializing router for chain_id: {chain_id}")

            if is_rise_network(normalized_name) or chain_id == 11155931:
                configured_address = None
                if network_config:
                    configured_address = network_config.get('contracts', {}).get('gaspump_router')
                self.router_address = configured_address or "0x5eC9BEaCe4a0f46F77945D54511e2b454cb8F38E"
                self.router_type = "gaspump"
                self.router_abi = self._get_gaspump_abi()
                self.logger.info("✅ Using Gaspump router for Rise Testnet")

            elif is_opn_network(normalized_name) or chain_id == 984:
                configured_address = None
                if network_config:
                    configured_address = network_config.get('contracts', {}).get('iopn_router')
                self.router_address = configured_address or "0xb489bce5c9c9364da2d1d1bc5ce4274f63141885"
                self.router_type = "iopn"
                self.router_abi = self._get_iopn_router_abi()
                self.logger.info("✅ Using IOPN router for OPN Testnet")

            elif chain_id == 688689:
                self.router_address = "0x1E656B2C6B6e91ef6E6A2B16475Df7b7D223e3c2"
                self.router_type = "faroswap"
                self.router_abi = self._get_gaspump_abi()
                self.logger.info("✅ Detected Pharos Atlantic - Faroswap router (not active)")

            else:
                self.logger.error(f"❌ Unsupported chain_id: {chain_id}")
                return

            # ✅ СОЗДАЕМ КОНТРАКТ ТОЛЬКО ЕСЛИ ЕСТЬ АДРЕС
            if self.router_address and self.router_abi:
                self.router_contract = self.web3.eth.contract(
                    address=Web3.to_checksum_address(self.router_address),
                    abi=self.router_abi
                )
                self.logger.info(f"✅ {self.router_type} router initialized: {self.router_address}")
            else:
                self.logger.info(f"ℹ️ No router address for {self.router_type or 'unknown'}")

        except Exception as e:
            self.logger.error(f"❌ Router initialization failed: {e}")
            self.router_contract = None

    def _get_gaspump_abi(self):
        """ABI для Gaspump Router"""
        return [
            {
                "inputs": [
                    {"internalType": "address", "name": "fromToken", "type": "address"},
                    {"internalType": "address", "name": "toToken", "type": "address"},
                    {"internalType": "uint256", "name": "fromTokenAmount", "type": "uint256"},
                    {"internalType": "uint256", "name": "expReturnAmount", "type": "uint256"},
                    {"internalType": "uint256", "name": "minReturnAmount", "type": "uint256"},
                    {"internalType": "address[]", "name": "mixAdapters", "type": "address[]"},
                    {"internalType": "address[]", "name": "mixPairs", "type": "address[]"},
                    {"internalType": "address[]", "name": "assetTo", "type": "address[]"},
                    {"internalType": "uint256", "name": "directions", "type": "uint256"},
                    {"internalType": "bytes[]", "name": "moreInfos", "type": "bytes[]"},
                    {"internalType": "bytes", "name": "feeData", "type": "bytes"},
                    {"internalType": "uint256", "name": "deadLine", "type": "uint256"}
                ],
                "name": "mixSwap",
                "outputs": [],
                "stateMutability": "payable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "address", "name": "fromToken", "type": "address"},
                    {"internalType": "address", "name": "toToken", "type": "address"},
                    {"internalType": "uint256", "name": "fromTokenAmount", "type": "uint256"}
                ],
                "name": "getMixSwapExpectedReturn",
                "outputs": [
                    {"internalType": "uint256", "name": "expReturnAmount", "type": "uint256"},
                    {"internalType": "uint256", "name": "minReturnAmount", "type": "uint256"},
                    {"internalType": "uint256[]", "name": "distribution", "type": "uint256[]"}
                ],
                "stateMutability": "view",
                "type": "function"
            }
        ]

    def _get_iopn_router_abi(self):
        """ABI для IOPN Router"""
        return [
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"},
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "name": "swapExactOPNForTokens",
                "outputs": [],
                "stateMutability": "payable",
                "type": "function"
            }
        ]

    def _get_erc20_abi(self):
        """ABI для ERC20 токенов"""
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

    def _get_wopn_abi(self):
        """ABI для WOPN (wrap)"""
        return [
            {
                "inputs": [],
                "name": "deposit",
                "outputs": [],
                "stateMutability": "payable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "wad", "type": "uint256"}
                ],
                "name": "withdraw",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            }
        ]

    async def get_token_balance(self, wallet, token_address: str) -> int:
        """Получение баланса токена"""
        try:
            if token_address == "0x0000000000000000000000000000000000000000":
                return self.web3.eth.get_balance(wallet.address)

            token_contract = self.web3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=self.erc20_abi
            )
            return token_contract.functions.balanceOf(wallet.address).call()
        except Exception as e:
            self.logger.error(f"❌ Error getting token balance: {e}")
            return 0

    async def get_token_decimals(self, token_address: str) -> int:
        """Получение decimals токена"""
        try:
            if token_address == "0x0000000000000000000000000000000000000000":
                return 18

            token_contract = self.web3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=self.erc20_abi
            )
            return token_contract.functions.decimals().call()
        except:
            return 18

    async def check_allowance(self, wallet, token_address: str, spender: str) -> int:
        """Проверка allowance для router"""
        try:
            if token_address == "0x0000000000000000000000000000000000000000":
                return 2 ** 256 - 1

            token_address_checksum = Web3.to_checksum_address(token_address)
            spender_checksum = Web3.to_checksum_address(spender)

            token_contract = self.web3.eth.contract(
                address=token_address_checksum,
                abi=self.erc20_abi
            )
            return token_contract.functions.allowance(wallet.address, spender_checksum).call()
        except Exception as e:
            self.logger.error(f"❌ Error checking allowance: {e}")
            return 0

    async def approve_token(self, wallet, token_address: str, amount: int) -> bool:
        """Approve токенов для router"""
        try:
            if token_address == "0x0000000000000000000000000000000000000000":
                return True

            token_address_checksum = Web3.to_checksum_address(token_address)
            router_address_checksum = Web3.to_checksum_address(self.router_address)

            # ✅ ПРОВЕРЯЕМ ТЕКУЩИЙ ALLOWANCE
            current_allowance = await self.check_allowance(wallet, token_address, self.router_address)
            if current_allowance >= amount:
                self.logger.info("✅ Allowance already sufficient")
                return True

            token_contract = self.web3.eth.contract(
                address=token_address_checksum,
                abi=self.erc20_abi
            )

            nonce = self.web3.eth.get_transaction_count(wallet.address)

            transaction = token_contract.functions.approve(
                router_address_checksum,
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

            self.logger.info(f"📝 Approval transaction sent: {tx_hash.hex()}")

            receipt = await asyncio.to_thread(
                self.web3.eth.wait_for_transaction_receipt,
                tx_hash,
                timeout=120
            )
            if receipt.status == 1:
                self.logger.info("✅ Approval successful")
                return True
            else:
                self.logger.error("❌ Approval failed")
                return False

        except Exception as e:
            self.logger.error(f"❌ Approval failed: {e}")
            return False

    def _get_swap_params(self, wallet_address, token_in, token_out):
        """✅ УПРОЩЕННЫЕ ПАРАМЕТРЫ ДЛЯ GASPUMP"""
        # Основные токены
        NATIVE_ETH = "0x0000000000000000000000000000000000000000"
        WETH = "0x4200000000000000000000000000000000000006"

        # ✅ УНИВЕРСАЛЬНЫЙ АДАПТЕР ДЛЯ ВСЕХ СВОПОВ
        mix_adapters = [Web3.to_checksum_address("0x4f8c8e05e946de09d768d062c5e969d1c8920c72")]

        # ✅ ПРОСТАЯ ЛОГИКА ДЛЯ ВСЕХ ПАР ТОКЕНОВ
        if token_in == NATIVE_ETH and token_out != WETH:
            # ETH -> любой токен (через WETH)
            mix_pairs = [Web3.to_checksum_address(WETH), Web3.to_checksum_address(token_out)]
            asset_to = [Web3.to_checksum_address(WETH), Web3.to_checksum_address(token_out),
                        Web3.to_checksum_address(wallet_address)]
            directions = 0
            self.logger.info(f"🔄 ETH -> {self._get_token_symbol(token_out)} (via WETH)")

        elif token_in != WETH and token_out == NATIVE_ETH:
            # любой токен -> ETH (через WETH)
            mix_pairs = [Web3.to_checksum_address(WETH), Web3.to_checksum_address(WETH)]
            asset_to = [Web3.to_checksum_address(WETH), Web3.to_checksum_address(WETH),
                        Web3.to_checksum_address(wallet_address)]
            directions = 0
            self.logger.info(f"🔄 {self._get_token_symbol(token_in)} -> ETH (via WETH)")

        elif token_in == WETH or token_out == WETH:
            # прямой своп с WETH
            mix_pairs = [Web3.to_checksum_address(token_out if token_in == WETH else token_in)]
            asset_to = [Web3.to_checksum_address(token_out), Web3.to_checksum_address(wallet_address)]
            directions = 0
            self.logger.info(f"🔄 Direct WETH swap")

        else:
            # ERC20 -> ERC20 (прямой путь)
            mix_pairs = [Web3.to_checksum_address(token_out)]
            asset_to = [Web3.to_checksum_address(token_out), Web3.to_checksum_address(wallet_address)]
            directions = 0
            self.logger.info(
                f"🔄 Direct ERC20: {self._get_token_symbol(token_in)} -> {self._get_token_symbol(token_out)}")

        return mix_adapters, mix_pairs, asset_to, directions

    async def execute_swap(self, wallet, token_in: str, token_out: str, amount_in: int) -> bool:
        """Универсальный метод выполнения свапа"""
        try:
            self.logger.info(
                f"🔄 GASPUMP: {self._get_token_symbol(token_in)} -> {self._get_token_symbol(token_out)}")

            # ✅ ПРАВИЛЬНЫЕ АДРЕСА
            NATIVE_ETH = "0x0000000000000000000000000000000000000000"
            ROUTER_NATIVE_ETH = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

            # Конвертируем адреса для роутера
            if token_in == NATIVE_ETH:
                token_in_checksum = Web3.to_checksum_address(ROUTER_NATIVE_ETH)
                actual_token_in = NATIVE_ETH
            else:
                token_in_checksum = Web3.to_checksum_address(token_in)
                actual_token_in = token_in

            if token_out == NATIVE_ETH:
                token_out_checksum = Web3.to_checksum_address(ROUTER_NATIVE_ETH)
            else:
                token_out_checksum = Web3.to_checksum_address(token_out)

            # ✅ ПОЛУЧАЕМ ПАРАМЕТРЫ СВОПА
            mix_adapters, mix_pairs, asset_to, directions = self._get_swap_params(
                wallet.address, token_in, token_out
            )

            # ✅ УПРОЩЕННЫЕ КОТИРОВКИ (50% slippage для тестовой сети)
            exp_return = amount_in // 2
            min_return = amount_in // 4

            self.logger.info(
                f"📊 Quotes: Expected {await self._format_amount(exp_return, token_in)}, Min {await self._format_amount(min_return, token_out)}")

            more_infos = [b'', b'']
            fee_data = b''
            deadline = self.web3.eth.get_block('latest')['timestamp'] + 1200

            # ✅ APPROVE ДЛЯ ERC20 ТОКЕНОВ
            if actual_token_in != NATIVE_ETH:
                allowance = await self.check_allowance(wallet, actual_token_in, self.router_address)
                self.logger.info(f"🔍 Current allowance: {allowance}, Required: {amount_in}")

                if allowance < amount_in:
                    self.logger.info("🔓 Approving tokens...")
                    if not await self.approve_token(wallet, actual_token_in, amount_in):
                        return False
                else:
                    self.logger.info("✅ Allowance sufficient")

            # Подготавливаем транзакцию
            nonce = self.web3.eth.get_transaction_count(wallet.address)

            transaction_params = {
                'from': wallet.address,
                'gas': 500000,
                'gasPrice': self.web3.eth.gas_price,
                'nonce': nonce,
                'chainId': self.web3.eth.chain_id
            }

            # ✅ ДОБАВЛЯЕМ VALUE ДЛЯ НАТИВНЫХ ТОКЕНОВ
            if actual_token_in == NATIVE_ETH:
                transaction_params['value'] = amount_in
                self.logger.info(f"💎 Adding native token value: {await self._format_amount(amount_in, token_in)}")

            transaction = self.router_contract.functions.mixSwap(
                token_in_checksum,
                token_out_checksum,
                amount_in,
                exp_return,
                min_return,
                mix_adapters,
                mix_pairs,
                asset_to,
                directions,
                more_infos,
                fee_data,
                deadline
            ).build_transaction(transaction_params)

            # Отправляем транзакцию
            signed_txn = wallet.account.sign_transaction(transaction)
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.raw_transaction)

            self.logger.info(f"📤 GASPUMP transaction sent: {tx_hash.hex()}")

            # Ждем подтверждения
            receipt = await asyncio.to_thread(
                self.web3.eth.wait_for_transaction_receipt,
                tx_hash,
                timeout=120
            )

            if receipt.status == 1:
                self.logger.info(f"✅ GASPUMP successful! TX: {tx_hash.hex()}")

                # ✅ ИСПОЛЬЗУЕМ НОРМАЛИЗОВАННОЕ ИМЯ СЕТИ ДЛЯ EXPLORER
                normalized_network = normalize_network_name('Rise Testnet')
                network_config = self.config.get_network_by_name(normalized_network)
                if network_config and network_config.get('explorer'):
                    explorer_url = network_config['explorer'].rstrip('/')
                    tx_explorer_url = f"{explorer_url}/tx/{tx_hash.hex()}"
                    self.logger.info(f"🌐 View in explorer: {tx_explorer_url}")

                return True
            else:
                self.logger.error(f"❌ GASPUMP failed: {tx_hash.hex()}")
                return False

        except Exception as e:
            self.logger.error(f"❌ GASPUMP execution failed: {e}")
            return False

    async def execute_random_swap(self, wallet, network_name: str) -> bool:
        """Диспетчер свапов в зависимости от сети"""
        normalized_network = normalize_network_name(network_name)

        if is_rise_network(normalized_network):
            return await self._execute_rise_swap(wallet, normalized_network)

        if is_opn_network(normalized_network):
            return await self._execute_opn_swap(wallet, normalized_network)

        self.logger.info(f"⚠️ Swap operations недоступны для сети {normalized_network}")
        return False

    async def _execute_rise_swap(self, wallet, normalized_network: str) -> bool:
        """SWAP через Gaspump для Rise Testnet"""
        try:
            if not self.router_contract:
                self.logger.error("❌ Router contract not initialized")
                return False

            self.logger.info(f"🔄 Starting random swap on Gaspump for {wallet.name}")

            tokens = self.config.get_tokens_for_network(normalized_network)
            if not tokens:
                self.logger.error(f"❌ No tokens configured for {normalized_network}")
                return False

            available_symbols = ['ETH', 'WETH', 'USDC', 'USDT', 'RISE', 'WBTC', 'MOG', 'PEPE']

            available_tokens = {}
            for symbol, address in tokens.items():
                if symbol in available_symbols:
                    available_tokens[symbol] = address

            if len(available_tokens) < 2:
                self.logger.error("❌ Not enough available tokens for swap")
                return False

            token_symbols = list(available_tokens.keys())
            token_in_symbol, token_out_symbol = random.sample(token_symbols, 2)
            token_in_address = available_tokens[token_in_symbol]
            token_out_address = available_tokens[token_out_symbol]

            self.logger.info(f"🎲 Selected swap pair: {token_in_symbol} -> {token_out_symbol}")

            balance = await self.get_token_balance(wallet, token_in_address)
            if balance == 0:
                self.logger.warning(f"⚠️ Zero balance for {token_in_symbol}")
                return False

            swap_percentage = Randomizer.get_random_percentage(0.5, 2.5)
            amount_in = int(balance * swap_percentage / 100)

            token_decimals = await self.get_token_decimals(token_in_address)
            min_amount = 10 ** (token_decimals - 3)  # 0.001 токена

            if amount_in < min_amount:
                amount_in = min_amount

            if amount_in > balance:
                self.logger.warning(f"⚠️ Not enough balance for swap")
                return False

            amount_in_formatted = await self._format_amount(amount_in, token_in_address)
            self.logger.info(
                f"💸 Swap amount: {amount_in_formatted} {token_in_symbol} ({swap_percentage:.2f}% of balance)")

            return await self.execute_swap(wallet, token_in_address, token_out_address, amount_in)

        except Exception as e:
            self.logger.error(f"❌ Rise swap failed: {e}")
            return False

    async def _execute_opn_swap(self, wallet, normalized_network: str) -> bool:
        """SWAP/обертка для OPN Testnet"""
        try:
            if self.router_type != "iopn" or not self.router_address:
                self.logger.error("❌ IOPN router is not configured")
                return False

            if not wallet.web3 or not wallet.web3.is_connected():
                network_config = self.config.get_network_by_name(normalized_network)
                if not network_config or not wallet.connect_to_network(network_config['rpc_url']):
                    self.logger.error("❌ Wallet not connected to OPN network")
                    return False

            tokens = self.config.get_tokens_for_network(normalized_network)
            if not tokens:
                self.logger.error(f"❌ No tokens configured for {normalized_network}")
                return False

            wopn_address = tokens.get('WOPN')
            if not wopn_address:
                self.logger.error("❌ WOPN token address not configured")
                return False

            target_symbols = ['OPNT', 'WOPN', 'tUSDT', 'tBNB']
            available_targets = [symbol for symbol in target_symbols if tokens.get(symbol)]
            if not available_targets:
                self.logger.error("❌ No target tokens configured for OPN swaps")
                return False

            balance = wallet.web3.eth.get_balance(wallet.address)
            if balance <= 0:
                self.logger.warning("⚠️ No OPN balance available for swap")
                return False

            gas_reserve = wallet.web3.to_wei(0.02, 'ether')
            spendable_balance = max(balance - gas_reserve, 0)
            if spendable_balance <= 0:
                self.logger.warning("⚠️ Not enough balance to keep gas reserve on OPN")
                return False

            swap_percentage = random.uniform(3, 10) / 100
            amount_in = int(balance * swap_percentage)
            min_amount = wallet.web3.to_wei(0.001, 'ether')
            if amount_in < min_amount:
                amount_in = min_amount
            if amount_in > spendable_balance:
                amount_in = spendable_balance

            if amount_in <= 0:
                self.logger.warning("⚠️ Swap amount is below threshold after adjustments")
                return False

            target_symbol = random.choice(available_targets)
            self.logger.info(
                f"🎯 OPN swap target: {target_symbol}, amount: {wallet.web3.from_wei(amount_in, 'ether'):.6f} OPN")

            if target_symbol == 'WOPN':
                return await self._wrap_opn_to_wopn(wallet, wopn_address, amount_in)

            target_address = tokens.get(target_symbol)
            if not target_address:
                self.logger.error(f"❌ Token address not configured for {target_symbol}")
                return False

            return await self._perform_opn_swap(wallet, amount_in, wopn_address, target_address, target_symbol)

        except Exception as e:
            self.logger.error(f"❌ OPN swap failed: {e}")
            return False

    async def _wrap_opn_to_wopn(self, wallet, wopn_address: str, amount_in: int) -> bool:
        """Обертка OPN -> WOPN"""
        try:
            wopn_contract = self.web3.eth.contract(
                address=Web3.to_checksum_address(wopn_address),
                abi=self._get_wopn_abi()
            )

            gas_price = max(self.web3.eth.gas_price, self.web3.to_wei(7, 'gwei'))
            transaction = wopn_contract.functions.deposit().build_transaction({
                'from': wallet.address,
                'value': amount_in,
                'gas': 120000,
                'gasPrice': gas_price,
                'nonce': self.web3.eth.get_transaction_count(wallet.address),
                'chainId': self.web3.eth.chain_id
            })

            signed_txn = wallet.account.sign_transaction(transaction)
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.raw_transaction)

            self.logger.info(f"📤 Wrapping OPN to WOPN: {tx_hash.hex()}")
            receipt = await asyncio.to_thread(
                self.web3.eth.wait_for_transaction_receipt,
                tx_hash,
                timeout=180
            )

            if receipt.status == 1:
                self.logger.info(f"✅ Wrapped {self.web3.from_wei(amount_in, 'ether'):.6f} OPN to WOPN")
                return True

            self.logger.error("❌ Wrap transaction failed")
            return False

        except Exception as e:
            self.logger.error(f"❌ Wrap to WOPN failed: {e}")
            return False

    async def _perform_opn_swap(self, wallet, amount_in: int, wopn_address: str,
                                target_address: str, target_symbol: str) -> bool:
        """Выполнение swapExactOPNForTokens"""
        try:
            if not self.router_contract:
                self.logger.error("❌ Router contract not initialized for OPN swaps")
                return False

            gas_price = max(self.web3.eth.gas_price, self.web3.to_wei(7, 'gwei'))
            deadline = self.web3.eth.get_block('latest')['timestamp'] + 1200
            path = [
                Web3.to_checksum_address(wopn_address),
                Web3.to_checksum_address(target_address)
            ]

            transaction = self.router_contract.functions.swapExactOPNForTokens(
                0,  # min amount disabled for тестовой сети
                path,
                wallet.address,
                deadline
            ).build_transaction({
                'from': wallet.address,
                'value': amount_in,
                'gas': 500000,
                'gasPrice': gas_price,
                'nonce': self.web3.eth.get_transaction_count(wallet.address),
                'chainId': self.web3.eth.chain_id
            })

            signed_txn = wallet.account.sign_transaction(transaction)
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.raw_transaction)
            self.logger.info(
                f"📤 swapExactOPNForTokens sent: {tx_hash.hex()} ({target_symbol})")

            receipt = await asyncio.to_thread(
                self.web3.eth.wait_for_transaction_receipt,
                tx_hash,
                timeout=180
            )

            if receipt.status == 1:
                self.logger.info(
                    f"✅ OPN swap successful! "
                    f"Spent {self.web3.from_wei(amount_in, 'ether'):.6f} OPN -> {target_symbol}"
                )
                return True

            self.logger.error("❌ swapExactOPNForTokens reverted")
            return False

        except Exception as e:
            self.logger.error(f"❌ Failed to execute swapExactOPNForTokens: {e}")
            return False

    def _get_token_symbol(self, token_address: str) -> str:
        """Получение символа токена по адресу"""
        try:
            for network in self.config.networks:
                network_name = network['name']
                tokens = self.config.get_tokens_for_network(network_name)
                if tokens:
                    for symbol, address in tokens.items():
                        if address.lower() == token_address.lower():
                            return symbol
            return "UNKNOWN"
        except Exception as e:
            self.logger.error(f"❌ Error getting token symbol: {e}")
            return "UNKNOWN"

    async def _format_amount(self, amount: int, token_address: str) -> str:
        """Форматирование суммы для логов"""
        decimals = await self.get_token_decimals(token_address)
        formatted = amount / (10 ** decimals)
        return f"{formatted:.6f}"
