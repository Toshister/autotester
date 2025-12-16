import asyncio
import random
import time
from web3 import Web3
from utils.logger import setup_logger
from utils.randomizer import Randomizer
from config.constants import (
    is_rise_network,
    is_opn_network,
    is_arc_network,
    is_pharos_network,
    normalize_network_name
)


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
        self.arc_native_placeholder = "0xEeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        self.permit2_address = None
        self.arc_curve_router_address = None
        self.arc_curve_router_contract = None
        self.arc_defi_router_address = None
        self.arc_defi_router_contract = None

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

            self.logger.debug(f"🔍 Initializing router for chain_id: {chain_id}")

            if is_opn_network(normalized_name) or chain_id == 984:
                configured_address = None
                if network_config:
                    configured_address = network_config.get('contracts', {}).get('iopn_router')
                self.router_address = configured_address or "0xb489bce5c9c9364da2d1d1bc5ce4274f63141885"
                self.router_type = "iopn"
                self.router_abi = self._get_iopn_router_abi()
                self.logger.info("✅ Using IOPN router for OPN Testnet")

            elif is_pharos_network(normalized_name) or chain_id == 688689:
                configured_address = None
                if network_config:
                    configured_address = network_config.get('contracts', {}).get('bitverse_router')
                # Используем найденный Bitverse universal router (execute)
                self.router_address = configured_address or "0x585fC3b498b1ABA1F0527663789361D3547aFC88"
                self.router_type = "pharos_bitverse"
                self.router_abi = self._get_universal_router_abi()
                self.logger.info("✅ Using Bitverse router for Pharos Atlantic")

            elif is_arc_network(normalized_name) or chain_id == 5042002:
                configured_address = None
                if network_config:
                    configured_address = network_config.get('contracts', {}).get('universal_router')
                    self.permit2_address = network_config.get('contracts', {}).get('permit2')
                    self.arc_curve_router_address = network_config.get('contracts', {}).get('curve_router')
                    self.arc_defi_router_address = network_config.get('contracts', {}).get('defi_router')
                self.router_address = configured_address or "0xbf4479C07Dc6fdc6dAa764A0ccA06969e894275F"
                self.router_type = "arc_universal"
                self.router_abi = self._get_universal_router_abi()
                self.permit2_address = self.permit2_address or "0x000000000022d473030f116ddee9f6b43ac78ba3"
                self.logger.info("✅ Using Universal router for Arc Testnet")

                # Инициализируем Curve router для альтернативных маршрутов
                curve_addr = self.arc_curve_router_address or "0xff5cb29241f002ffed2eaa224e3e996d24a6e8d1"
                try:
                    self.arc_curve_router_contract = self.web3.eth.contract(
                        address=Web3.to_checksum_address(curve_addr),
                        abi=self._get_arc_router_abi()
                    )
                    self.logger.info(f"✅ Curve router available for Arc: {curve_addr}")
                except Exception as e:
                    self.logger.warning(f"⚠️ Failed to init Curve router for Arc: {e}")

                defi_addr = self.arc_defi_router_address or "0x284C5Afc100ad14a458255075324fA0A9dfd66b1"
                try:
                    self.arc_defi_router_contract = self.web3.eth.contract(
                        address=Web3.to_checksum_address(defi_addr),
                        abi=self._get_arc_defi_router_abi()
                    )
                    self.logger.info(f"✅ DeFi router available for Arc: {defi_addr}")
                except Exception as e:
                    self.logger.warning(f"⚠️ Failed to init DeFi router for Arc: {e}")

            elif is_rise_network(normalized_name) or chain_id == 11155931:
                self.logger.warning("⚠️ Rise Testnet swaps via Gaspump disabled in this build")
                self.router_address = None
                self.router_type = None
                self.router_abi = None

            else:
                self.logger.warning(f"ℹ️ Swap router not configured for chain_id: {chain_id}")
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
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"},
                    {"internalType": "address", "name": "to", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "name": "swapExactTokensForOPN",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            }
        ]

    def _get_arc_router_abi(self):
        """ABI для Curve router в Arc"""
        return [
            {
                "inputs": [
                    {"internalType": "address[11]", "name": "_route", "type": "address[11]"},
                    {"internalType": "uint256[4][5]", "name": "_swap_params", "type": "uint256[4][5]"},
                    {"internalType": "uint256", "name": "_amount", "type": "uint256"},
                    {"internalType": "uint256", "name": "_min_dy", "type": "uint256"}
                ],
                "name": "exchange",
                "outputs": [
                    {"internalType": "uint256", "name": "amountOut", "type": "uint256"}
                ],
                "stateMutability": "payable",
                "type": "function"
            }
        ]

    def _get_arc_defi_router_abi(self):
        """ABI для дополнительного Arc роутера (swapExactTokensForTokens / findBestPath)"""
        return [
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"},
                    {"internalType": "address", "name": "to", "type": "address"}
                ],
                "name": "swapExactTokensForTokens",
                "outputs": [
                    {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}
                ],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "address", "name": "tokenIn", "type": "address"},
                    {"internalType": "address", "name": "tokenOut", "type": "address"}
                ],
                "name": "findBestPath",
                "outputs": [
                    {"internalType": "address[]", "name": "path", "type": "address[]"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "address[]", "name": "path", "type": "address[]"}
                ],
                "name": "getAmountsOut",
                "outputs": [
                    {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}
                ],
                "stateMutability": "view",
                "type": "function"
            }
        ]

    def _get_universal_router_abi(self):
        """Краткий ABI Universal Router execute"""
        return [
            {
                "name": "execute",
                "type": "function",
                "stateMutability": "payable",
                "inputs": [
                    {"internalType": "bytes", "name": "commands", "type": "bytes"},
                    {"internalType": "bytes[]", "name": "inputs", "type": "bytes[]"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
                ],
                "outputs": []
            },
            {"inputs": [], "name": "WETH9", "outputs": [{"internalType": "address", "name": "", "type": "address"}],
             "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "PERMIT2", "outputs": [{"internalType": "address", "name": "", "type": "address"}],
             "stateMutability": "view", "type": "function"}
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

    async def _snapshot_token_balances(self, wallet, tokens: dict) -> dict:
        """Фиксируем баланс нативки и всех токенов для кошелька перед swap"""
        snapshot = {"__native__": wallet.web3.eth.get_balance(wallet.address) if wallet.web3 else 0}
        zero_address = "0x0000000000000000000000000000000000000000"

        for symbol, address in tokens.items():
            if not address or address.lower() == zero_address:
                continue
            try:
                code = wallet.web3.eth.get_code(Web3.to_checksum_address(address))
                if not code or code == b"\x00":
                    self.logger.debug(
                        f"ℹ️ Skipping {symbol} balance check on {wallet.web3.eth.chain_id}: "
                        f"no contract code at {address}"
                    )
                    continue
            except Exception as e:
                self.logger.warning(
                    f"⚠️ Skipping {symbol} balance check on {wallet.web3.eth.chain_id}: {e}"
                )
                continue

            snapshot[symbol] = await self.get_token_balance(wallet, address)

        return snapshot

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

    async def approve_token_for_spender(self, wallet, token_address: str, spender: str, amount: int) -> bool:
        """Approve токенов для указанного spender"""
        try:
            if token_address == "0x0000000000000000000000000000000000000000":
                return True

            token_address_checksum = Web3.to_checksum_address(token_address)
            spender_checksum = Web3.to_checksum_address(spender)

            # ✅ ПРОВЕРЯЕМ ТЕКУЩИЙ ALLOWANCE
            token_contract = self.web3.eth.contract(
                address=token_address_checksum,
                abi=self.erc20_abi
            )
            current_allowance = token_contract.functions.allowance(wallet.address, spender_checksum).call()
            if current_allowance >= amount:
                self.logger.info("✅ Allowance already sufficient")
                return True

            nonce = self.web3.eth.get_transaction_count(wallet.address)
            transaction = token_contract.functions.approve(
                spender_checksum,
                amount
            ).build_transaction({
                'from': wallet.address,
                'gas': 120000,
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

    async def execute_random_swap(self, wallet, network_name: str) -> bool:
        """Диспетчер свапов в зависимости от сети"""
        normalized_network = normalize_network_name(network_name)

        if is_rise_network(normalized_network):
            self.logger.warning(f"⚠️ Swap operations disabled for {normalized_network}")
            return False

        if is_pharos_network(normalized_network):
            return await self._execute_pharos_swap(wallet, normalized_network)

        if is_arc_network(normalized_network):
            return await self._execute_arc_swap(wallet, normalized_network)

        if is_opn_network(normalized_network):
            return await self._execute_opn_swap(wallet, normalized_network)

        self.logger.info(f"⚠️ Swap operations недоступны для сети {normalized_network}")
        return False

    def _build_arc_route(self, base_route: list, base_params: list, reverse: bool = False) -> dict:
        """Собирает маршруты для Curve router (padding + опциональный реверс)"""
        zero_address = "0x0000000000000000000000000000000000000000"

        if reverse:
            trimmed_route = [addr for addr in base_route if addr != zero_address]
            reversed_route = list(reversed(trimmed_route))
            reversed_route += [zero_address] * max(11 - len(reversed_route), 0)

            used_params = [row for row in base_params if any(row)]
            reversed_params = list(reversed(used_params))
            reversed_params += [[0, 0, 0, 0]] * max(5 - len(reversed_params), 0)

            return {"route": reversed_route[:11], "swap_params": reversed_params[:5]}

        padded_route = base_route + [zero_address] * max(11 - len(base_route), 0)
        padded_params = base_params + [[0, 0, 0, 0]] * max(5 - len(base_params), 0)
        return {"route": padded_route[:11], "swap_params": padded_params[:5]}

    def _get_arc_route_templates(self, tokens: dict) -> dict:
        """Маршруты для Arc на Curve (расширенный список)"""
        native = self.arc_native_placeholder

        wusdc = tokens.get('WUSDC')
        rusdc = tokens.get('rUSDC')
        eurc = tokens.get('EURC')
        ca4f = tokens.get('CA4F')
        tst = tokens.get('TST')
        warc = tokens.get('wARC')
        dusdt = tokens.get('dUSDT')
        brid = tokens.get('BRID')
        bbtoken = tokens.get('bbToken')

        pools = {
            "rusdc": "0xa87680b380207f6eb2ab0613401277124659d7f3",
            "warc": "0xe82a94d78120d06b9ef6709ee22a3696a0ecf520",
            "dusdt": "0xdfcefa1350a88deb1db0e7ef2cf39dbecb7ba569",
            "brid": "0xadbc6745ce0248ef470d2e344d95ad7442de6041",
            "bbtoken": "0xf2f812214d2b9f83ae430e06962dd889e19b9eb3",
            # Updated per working EURC->USDC swap (0x74a127...364): router sent funds to this pool
            "eurc": "0x269b47978f4348c96f521658ef452ff85906fcfe",
            "tst": "0x16de4cc9c6271c1e06d0889d48648bc42746b4eb",
            "ca4f": "0x3b9624be2f1280fc927532f44daf15901260d9ec"
        }

        templates = {}

        if native and wusdc:
            base_route = [native, wusdc, wusdc]
            base_params = [[0, 0, 8, 0]]
            templates['WUSDC'] = {
                "forward": self._build_arc_route(base_route, base_params),
                "reverse": self._build_arc_route(base_route, base_params, reverse=True)
            }

        if native and wusdc and rusdc:
            base_route = [native, wusdc, wusdc, pools["rusdc"], rusdc]
            base_params = [[0, 0, 8, 0], [0, 1, 1, 10]]
            templates['rUSDC'] = {
                "forward": self._build_arc_route(base_route, base_params),
                "reverse": self._build_arc_route([rusdc, pools["rusdc"], wusdc, wusdc, native], [[1, 0, 1, 10], [0, 0, 8, 0]])
            }

        if native and wusdc and warc:
            base_route = [native, wusdc, wusdc, pools["warc"], warc]
            base_params = [[0, 0, 8, 0], [0, 1, 1, 20]]
            templates['wARC'] = {
                "forward": self._build_arc_route(base_route, base_params),
                "reverse": self._build_arc_route(base_route, base_params, reverse=True)
            }

        if native and wusdc and dusdt:
            base_route = [native, wusdc, wusdc, pools["dusdt"], dusdt]
            base_params = [[0, 0, 8, 0], [0, 1, 1, 10]]
            templates['dUSDT'] = {
                "forward": self._build_arc_route(base_route, base_params),
                "reverse": self._build_arc_route(base_route, base_params, reverse=True)
            }

        if native and wusdc and brid:
            base_route = [native, wusdc, wusdc, pools["brid"], brid]
            base_params = [[0, 0, 8, 0], [0, 1, 1, 20]]
            templates['BRID'] = {
                "forward": self._build_arc_route(base_route, base_params),
                "reverse": self._build_arc_route(base_route, base_params, reverse=True)
            }

        if native and wusdc and bbtoken:
            base_route = [native, wusdc, wusdc, pools["bbtoken"], bbtoken]
            base_params = [[0, 0, 8, 0], [0, 1, 1, 10]]
            templates['bbToken'] = {
                "forward": self._build_arc_route(base_route, base_params),
                "reverse": self._build_arc_route(base_route, base_params, reverse=True)
            }

        if native and wusdc and eurc:
            base_route = [native, wusdc, wusdc, pools["eurc"], eurc]
            base_params = [[0, 0, 8, 0], [1, 0, 1, 10]]
            templates['EURC'] = {
                "forward": self._build_arc_route(base_route, base_params),
                "reverse": self._build_arc_route(base_route, base_params, reverse=True)
            }

        if native and wusdc and eurc and tst:
            base_route = [native, wusdc, wusdc, pools["eurc"], eurc, pools["tst"], tst]
            base_params = [[0, 0, 8, 0], [1, 0, 1, 10], [0, 1, 1, 20]]
            templates['TST'] = {
                "forward": self._build_arc_route(base_route, base_params),
                "reverse": self._build_arc_route(base_route, base_params, reverse=True)
            }

        if native and wusdc and eurc and ca4f:
            base_route = [native, wusdc, wusdc, pools["eurc"], eurc, pools["ca4f"], ca4f]
            base_params = [[0, 0, 8, 0], [1, 0, 1, 10], [1, 0, 1, 20]]
            templates['CA4F'] = {
                "forward": self._build_arc_route(base_route, base_params),
                "reverse": self._build_arc_route(base_route, base_params, reverse=True)
            }

        return templates

    async def _execute_pharos_swap(self, wallet, normalized_network: str) -> bool:
        """SWAP для Pharos Atlantic через Bitverse Universal Router (ETH/WETH, WBTC, USDT)"""
        try:
            if self.router_type != "pharos_bitverse" or not self.router_contract:
                self.logger.error("❌ Bitverse router is not configured for Pharos")
                return False

            if not wallet.web3 or not wallet.web3.is_connected():
                network_config = self.config.get_network_by_name(normalized_network)
                if not network_config or not wallet.connect_to_network(network_config['rpc_url']):
                    self.logger.error("❌ Wallet not connected to Pharos network")
                    return False

            tokens = self.config.get_tokens_for_network(normalized_network)
            if not tokens:
                self.logger.error("❌ No tokens configured for Pharos Atlantic")
                return False

            for required in ['USDT', 'WETH', 'WBTC']:
                if not tokens.get(required):
                    self.logger.error(f"❌ Missing token address for {required} on Pharos")
                    return False

            balance_snapshot = await self._snapshot_token_balances(wallet, tokens)
            token_balances = {sym: bal for sym, bal in balance_snapshot.items() if sym != '__native__' and bal > 0}
            self.logger.debug(
                f"💰 Pharos balances | tokens: {', '.join(token_balances.keys()) if token_balances else 'none'}"
            )

            amount_presets = {
                'USDT': {'min': 30.0, 'max': 80.0, 'precisions': [1, 0.1, 0.01]},
                'WETH': {'min': 0.008, 'max': 0.025, 'precisions': [0.001, 0.0001]},
                'WBTC': {'min': 0.00025, 'max': 0.0012, 'precisions': [0.0001, 0.00001]}
            }

            decimals_cache = {}

            async def get_decimals(symbol: str) -> int:
                if symbol not in decimals_cache:
                    decimals_cache[symbol] = await self.get_token_decimals(tokens.get(symbol))
                return decimals_cache[symbol]

            async def choose_amount(symbol: str, balance_raw: int) -> int:
                preset = amount_presets.get(symbol)
                if not preset or balance_raw <= 0:
                    return 0

                decimals = await get_decimals(symbol)
                min_raw = int(preset['min'] * (10 ** decimals))
                max_raw = int(preset['max'] * (10 ** decimals))
                precision = random.choice(preset['precisions'])
                precision_str = f"{precision:.10f}".rstrip("0").rstrip(".")
                digits = len(precision_str.split(".")[1]) if "." in precision_str else 0

                amount_float = round(random.uniform(preset['min'], preset['max']), digits)
                amount_raw = int(amount_float * (10 ** decimals))
                amount_raw = max(min_raw, min(amount_raw, max_raw))

                spend_cap = int(balance_raw * 0.95)
                if spend_cap <= 0:
                    return 0
                amount_raw = min(amount_raw, spend_cap)
                return amount_raw if amount_raw > 0 else 0

            swap_pairs = [
                ('USDT', 'WETH'),
                ('USDT', 'WBTC'),
                ('WETH', 'USDT'),
                ('WBTC', 'USDT')
            ]
            random.shuffle(swap_pairs)

            base_fee = self.web3.eth.gas_price
            gas_price = max(base_fee, self.web3.to_wei(1, 'gwei'))
            deadline = int(time.time()) + 1800
            command_byte = b"\x10"

            def build_bitverse_input(token_in: str, token_out: str, amount: int) -> bytes:
                """
                Сборка bytes для Bitverse execute по фактической структуре успешных вызовов (35 слов, offset 0x360):
                [0]=0x60, [1]=0xA0, [2]=deadline, [3]=1, [4]=0x100..., [5]=1, [6]=0x20, [7]=0x360,
                [8]=0x40, [9]=0x80, [10]=0x3, [11]=0x060c0f..., [12]=0x3, [13]=0x60, [14]=0x200, [15]=0x260,
                [16]=0x180, [17]=0x20, [18]=token_out, [19]=token_in, [20]=0x0bb8, [21]=0x5,
                [22]=0, [23]=0, [24]=amount, [25]=0, [26]=0x120, [27]=0x1, [28]=0, [29]=0x40,
                [30]=token_in, [31]=amount, [32]=0x40, [33]=token_out, [34]=0
                """
                t_in = int(token_in, 16)
                t_out = int(token_out, 16)
                words = [0] * 35
                words[0] = 0x60
                words[1] = 0xA0
                words[2] = deadline
                words[3] = 0x1
                words[4] = int("0100000000000000000000000000000000000000000000000000000000000000", 16)
                words[5] = 0x1
                words[6] = 0x20
                words[7] = 0x360
                words[8] = 0x40
                words[9] = 0x80
                words[10] = 0x3
                words[11] = int("060c0f0000000000000000000000000000000000000000000000000000000000", 16)
                words[12] = 0x3
                words[13] = 0x60
                words[14] = 0x200
                words[15] = 0x260
                words[16] = 0x180
                words[17] = 0x20
                words[18] = t_out
                words[19] = t_in
                words[20] = 0x0bb8
                words[21] = 0x5
                words[22] = 0
                words[23] = 0
                words[24] = amount
                words[25] = 0
                words[26] = 0x120
                words[27] = 0x1
                words[28] = 0
                words[29] = 0x40
                words[30] = t_in
                words[31] = amount
                words[32] = 0x40
                words[33] = t_out
                words[34] = 0
                return b"".join(w.to_bytes(32, byteorder='big') for w in words)

            for from_symbol, to_symbol in swap_pairs:
                balance_raw = token_balances.get(from_symbol, 0)
                if balance_raw <= 0:
                    continue

                amount_in = await choose_amount(from_symbol, balance_raw)
                if amount_in <= 0:
                    continue

                if not await self.approve_token(wallet, tokens.get(from_symbol), amount_in):
                    self.logger.warning(f"⚠️ Approval failed for {from_symbol}, trying next direction")
                    continue

                commands = command_byte
                swap_input = build_bitverse_input(tokens.get(from_symbol), tokens.get(to_symbol), amount_in)
                inputs = [swap_input]

                try:
                    tx = self.router_contract.functions.execute(
                        commands,
                        inputs,
                        deadline
                    ).build_transaction({
                        'from': wallet.address,
                        'value': 0,
                        'gas': 900000,
                        'maxFeePerGas': gas_price,
                        'maxPriorityFeePerGas': gas_price,
                        'nonce': self.web3.eth.get_transaction_count(wallet.address),
                        'chainId': self.web3.eth.chain_id
                    })

                    self.logger.info(
                        f"📤 Pharos swap {from_symbol}->{to_symbol} via Bitverse, amount: "
                        f"{await self._format_amount(amount_in, tokens.get(from_symbol))}"
                    )

                    signed_txn = wallet.account.sign_transaction(tx)
                    tx_hash = self.web3.eth.send_raw_transaction(signed_txn.raw_transaction)
                    receipt = await asyncio.to_thread(
                        self.web3.eth.wait_for_transaction_receipt,
                        tx_hash,
                        timeout=240
                    )

                    if receipt.status == 1:
                        self.logger.info(f"✅ Pharos swap successful: {tx_hash.hex()}")
                        return True

                    self.logger.error("❌ Pharos swap reverted, trying another direction")
                except Exception as e:
                    self.logger.error(f"❌ Pharos swap build/send failed: {e}")

            self.logger.warning("⚠️ No eligible Pharos swap executed (insufficient balances or all attempts failed)")
            return False

        except Exception as e:
            self.logger.error(f"❌ Pharos swap failed: {e}")
            return False

    async def _execute_arc_defi_swap(self, wallet, tokens: dict, nonzero_tokens: dict) -> bool:
        """SWAP через DeFi router (defi-on-arc) с мин. суммой 5 USDC и балансом >=80 USDC"""
        try:
            if not self.arc_defi_router_contract:
                return False

            usdc_addr = tokens.get('USDC')
            if not usdc_addr:
                self.logger.error("❌ USDC address missing for DeFi swap")
                return False

            usdc_balance = nonzero_tokens.get('USDC', 0)
            usdc_decimals = await self.get_token_decimals(usdc_addr)
            min_balance_required = int(80 * (10 ** usdc_decimals))
            if usdc_balance < min_balance_required:
                self.logger.debug("ℹ️ USDC balance below 80, skipping DeFi router")
                return False

            target_symbols = ['EURC', 'SRAC', 'RACS', 'SACS', 'KITTY', 'DOGG']
            available_targets = [sym for sym in target_symbols if tokens.get(sym)]
            if not available_targets:
                self.logger.error("❌ No target tokens configured for DeFi swap")
                return False

            target_symbol = random.choice(available_targets)
            target_addr = tokens.get(target_symbol)

            spendable = usdc_balance
            min_swap = int(5 * (10 ** usdc_decimals))
            max_swap = int(5.5 * (10 ** usdc_decimals))
            # выбираем 5-5.5 USDC, шаг 0.001
            amount_usdc = round(random.uniform(5, 5.5), 3)
            amount_in = int(amount_usdc * (10 ** usdc_decimals))
            if amount_in < min_swap:
                amount_in = min_swap
            if amount_in > max_swap:
                amount_in = max_swap
            if amount_in > spendable:
                self.logger.warning("⚠️ Not enough USDC to meet fixed swap amount for DeFi router")
                return False

            if not await self.approve_token_for_spender(wallet, usdc_addr, self.arc_defi_router_contract.address, amount_in):
                return False

            try:
                path = self.arc_defi_router_contract.functions.findBestPath(
                    Web3.to_checksum_address(usdc_addr),
                    Web3.to_checksum_address(target_addr)
                ).call()
                if not path or len(path) < 2:
                    path = [Web3.to_checksum_address(usdc_addr), Web3.to_checksum_address(target_addr)]
            except Exception:
                path = [Web3.to_checksum_address(usdc_addr), Web3.to_checksum_address(target_addr)]

            try:
                amounts_out = self.arc_defi_router_contract.functions.getAmountsOut(amount_in, path).call()
                min_out = int(amounts_out[-1] * 0.8) if amounts_out else 0  # широкий slippage 20%
            except Exception:
                min_out = 0

            gas_price = max(self.web3.eth.gas_price, self.web3.to_wei(5, 'gwei'))
            tx = self.arc_defi_router_contract.functions.swapExactTokensForTokens(
                amount_in,
                min_out,
                path,
                wallet.address
            ).build_transaction({
                'from': wallet.address,
                'value': 0,
                'gas': 700000,
                'gasPrice': gas_price,
                'nonce': self.web3.eth.get_transaction_count(wallet.address),
                'chainId': self.web3.eth.chain_id
            })

            self.logger.info(
                f"📤 Arc swap via DeFi router USDC -> {target_symbol}, amount: {await self._format_amount(amount_in, usdc_addr)}"
            )

            signed_txn = wallet.account.sign_transaction(tx)
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.raw_transaction)
            receipt = await asyncio.to_thread(
                self.web3.eth.wait_for_transaction_receipt,
                tx_hash,
                timeout=240
            )
            if receipt.status == 1:
                self.logger.info(f"✅ Arc DeFi router swap successful: {tx_hash.hex()}")
                return True

            self.logger.error("❌ Arc DeFi router swap reverted")
            return False

        except Exception as e:
            self.logger.error(f"❌ Arc DeFi router swap failed: {e}")
            return False

    async def _execute_arc_swap(self, wallet, normalized_network: str, _retry: bool = False) -> bool:
        """SWAP для Arc Testnet: случайно Universal Router (Synthra) или Curve"""
        try:
            if self.router_type != "arc_universal" or not self.router_contract:
                self.logger.error("❌ Universal router is not configured for Arc")
                return False

            if not wallet.web3 or not wallet.web3.is_connected():
                network_config = self.config.get_network_by_name(normalized_network)
                if not network_config or not wallet.connect_to_network(network_config['rpc_url']):
                    self.logger.error("❌ Wallet not connected to Arc network")
                    return False

            tokens = self.config.get_tokens_for_network(normalized_network)
            if not tokens:
                self.logger.error(f"❌ No tokens configured for {normalized_network}")
                return False

            network_config = self.config.get_network_by_name(normalized_network) or {}
            native_symbol = network_config.get('native_token', 'USDC')
            wusdc_addr = tokens.get('WUSDC')
            syn_addr = tokens.get('SYN')
            usdt_addr = tokens.get('USDT')
            if not wusdc_addr:
                self.logger.error("❌ WUSDC address not configured for Arc")
                return False

            balance_snapshot = await self._snapshot_token_balances(wallet, tokens)
            native_balance = balance_snapshot.get('__native__', 0)
            nonzero_tokens = {sym: bal for sym, bal in balance_snapshot.items() if sym != '__native__' and bal > 0}
            self.logger.debug(
                f"💰 Swap balance snapshot | native: {self.web3.from_wei(native_balance, 'ether'):.6f} "
                f"| tokens: {', '.join(nonzero_tokens.keys()) if nonzero_tokens else 'none'}")

            usdc_addr = tokens.get('USDC')
            usdc_decimals = await self.get_token_decimals(usdc_addr or "0x0")
            min_defi_balance = int(40 * (10 ** usdc_decimals))
            allow_defi_router = (
                self.arc_defi_router_contract is not None
                and nonzero_tokens.get('USDC', 0) >= min_defi_balance
            )

            # Минимальные суммы (в токенах) для нестабильных маршрутов, чтобы избежать ревёртов на мелочи
            min_amount_tokens = {
                'wARC': 0.01,
                'dUSDT': 0.01,
                'bbToken': 0.01,
                'BRID': 0.05,
                'TST': 0.2,
                # Усиливаем минималки для проблемных целей на Curve
                'CA4F': 1.0,
                'EURC': 1.0,
                'rUSDC': 0.3
            }

            async def apply_min_amount(symbol: str, amount: int) -> int:
                """Применить минимальную сумму для конкретного токена (в wei/единицах токена)"""
                if symbol not in min_amount_tokens:
                    return amount
                token_addr = tokens.get(symbol)
                decimals = await self.get_token_decimals(token_addr or "0x0")
                min_raw = int(min_amount_tokens[symbol] * (10 ** decimals))
                return max(amount, min_raw)

            # Пока Universal Router на Arc нестабилен, приоритет Curve
            use_curve = True
            route_templates = self._get_arc_route_templates(tokens) if use_curve else {}
            if use_curve and (not route_templates or not self.arc_curve_router_contract):
                self.logger.debug("ℹ️ No Curve routes available or curve router missing, falling back to Universal")
                use_curve = False

            # Маршруты, которые стабильно ревертят на Curve/Universal — не выбираем как цели/источники
            curve_blacklist = {'TST', 'EURC', 'CA4F'}
            async def arc_reroll():
                if _retry:
                    return False
                self.logger.info("🔁 Arc swap reroll: trying a different route in the same iteration")
                return await self._execute_arc_swap(wallet, normalized_network, _retry=True)

            # Попробуем новый DeFi роутер с равной вероятностью (~1/3), если хватает USDC
            if allow_defi_router and random.random() < 0.34:
                success_defi = await self._execute_arc_defi_swap(wallet, tokens, nonzero_tokens)
                if success_defi:
                    return True
                self.logger.info("ℹ️ DeFi router swap failed or skipped, falling back to Curve/Universal")

            native_to_token = random.random() < 0.75

            # Универсальные токены для Universal Router (также нужны в Curve валидации)
            allowed_universal_symbols = {'USDC', 'WUSDC', 'SYN', 'USDT'}

            def pick_token_from_balances(allowed=None):
                allowed_set = set(allowed) if allowed else None
                candidates = {
                    sym: bal for sym, bal in nonzero_tokens.items()
                    if not allowed_set or sym in allowed_set
                }
                if not candidates:
                    return None, 0
                choice = random.choice(list(candidates.keys()))
                return choice, candidates[choice]

            if native_to_token:
                from_symbol = native_symbol  # источник — native
                balance = native_balance
                if balance <= 0:
                    # Если нет native, пробуем токены
                    native_to_token = False
                    from_symbol, balance = pick_token_from_balances(['SYN', 'USDT', 'WUSDC'])
                    if not from_symbol or balance <= 0:
                        self.logger.warning("⚠️ No balance available for Arc swap (neither native nor tokens)")
                        return False
            else:
                from_symbol, balance = pick_token_from_balances(['SYN', 'USDT', 'WUSDC'])
                if not from_symbol or balance <= 0:
                    # fallback к native
                    native_to_token = True
                    balance = native_balance
                    from_symbol = native_symbol
                    if balance <= 0:
                        self.logger.warning("⚠️ No balance available for Arc swap (tokens and native empty)")
                        return False

            swap_percentage = random.uniform(0.3, 1.5) / 100
            amount_in = int(balance * swap_percentage)
            if amount_in <= 0:
                self.logger.warning("⚠️ Swap amount is below threshold after adjustments")
                return False

            gas_price = max(self.web3.eth.gas_price, self.web3.to_wei(5, 'gwei'))

            if use_curve:
                # ---------- Curve branch ----------
                templates = self._get_arc_route_templates(tokens)
                arc_tokens = list(templates.keys())
                if not arc_tokens:
                    self.logger.debug("ℹ️ Curve routes empty, fallback to Universal")
                    use_curve = False

                if use_curve:
                    target_symbol = None
                    route_data = None
                    if native_to_token:
                        allowed_forward = [t for t in arc_tokens if t not in curve_blacklist]
                        if not allowed_forward:
                            self.logger.debug("ℹ️ No allowed Curve targets after blacklist, fallback to Universal")
                            use_curve = False
                        else:
                            target_symbol = random.choice(allowed_forward)
                            route_data = templates.get(target_symbol, {}).get('forward')
                            # Отбрасываем Curve для целей TST/EURC/CA4F если сумма < 1 USDC
                            if target_symbol in {'TST', 'EURC', 'CA4F'} and amount_in < self.web3.to_wei(1, 'ether'):
                                self.logger.debug(f"ℹ️ Amount too low for Curve target {target_symbol}, skipping")
                                use_curve = False
                                route_data = None
                    else:
                        # Берем только те токены, по которым есть баланс
                        candidates = [t for t in arc_tokens if t in nonzero_tokens and t not in curve_blacklist]
                        if not candidates:
                            self.logger.warning("⚠️ No token balance for Curve swap")
                            use_curve = False
                        else:
                            from_symbol = random.choice(candidates)
                            target_symbol = native_symbol
                            route_data = templates.get(from_symbol, {}).get('reverse')

                    if not route_data:
                        self.logger.warning("⚠️ No Curve route for selected swap, fallback to Universal")
                        use_curve = False

                if use_curve:
                    zero_address = "0x0000000000000000000000000000000000000000"
                    zero_address = "0x0000000000000000000000000000000000000000"
                    if native_to_token:
                        balance_available = native_balance
                        gas_reserve = wallet.web3.to_wei(0.05, 'ether')
                        spendable = max(balance_available - gas_reserve, 0)
                    else:
                        from_address = tokens.get(from_symbol)
                        balance_available = nonzero_tokens.get(from_symbol, 0)
                        spendable = balance_available

                    if spendable <= 0:
                        self.logger.warning("⚠️ No balance for Curve swap")
                        return False

                    amount_in = int(spendable * swap_percentage)
                    amount_in = await apply_min_amount(from_symbol, amount_in)
                    if amount_in <= 0:
                        amount_in = min(spendable, 1)
                    if native_to_token and amount_in > spendable:
                        amount_in = spendable
                    if amount_in <= 0:
                        self.logger.warning("⚠️ Swap amount is below threshold after adjustments")
                        return False

                    # Если выбранный токен (в токен->native) не поддерживается Universal и Curve, пропускаем
                    if not native_to_token:
                        from_symbol_upper = (from_symbol or "").upper()
                        universal_allowed = from_symbol_upper in allowed_universal_symbols
                        curve_allowed = from_symbol_upper in arc_tokens
                        if not universal_allowed and not curve_allowed:
                            self.logger.warning(f"⚠️ Token {from_symbol} not supported by Universal or Curve, skipping swap")
                            return False

                    if not native_to_token:
                        from_address = tokens.get(from_symbol)
                        if not await self.approve_token(wallet, from_address, amount_in):
                            return False

                    route = []
                    for addr in route_data['route']:
                        if addr.lower() == zero_address:
                            route.append(zero_address)
                        else:
                            route.append(Web3.to_checksum_address(addr))

                    swap_params = [list(map(int, row)) for row in route_data['swap_params']]

                    transaction = self.arc_curve_router_contract.functions.exchange(
                        route,
                        swap_params,
                        amount_in,
                        0
                    ).build_transaction({
                        'from': wallet.address,
                        'value': amount_in if native_to_token else 0,
                        'gas': 1500000,
                        'gasPrice': gas_price,
                        'nonce': self.web3.eth.get_transaction_count(wallet.address),
                        'chainId': self.web3.eth.chain_id
                    })

                    spent_readable = await self._format_amount(
                        amount_in,
                        zero_address if native_to_token else tokens.get(from_symbol)
                    )
                    self.logger.info(f"📤 Arc swap via Curve {from_symbol} -> {target_symbol}, amount: {spent_readable}")

                    signed_txn = wallet.account.sign_transaction(transaction)
                    tx_hash = self.web3.eth.send_raw_transaction(signed_txn.raw_transaction)
                    receipt = await asyncio.to_thread(
                        self.web3.eth.wait_for_transaction_receipt,
                        tx_hash,
                        timeout=240
                    )
                    if receipt.status == 1:
                        self.logger.info(f"✅ Arc Curve swap successful: {tx_hash.hex()}")
                        return True
                    self.logger.error("❌ Arc Curve swap failed (reverted), attempting Universal fallback")
                    # Don't return False here, let it fall through to Universal Router

            # ---------- Universal Router branch ----------
            V3_SWAP_EXACT_IN = b"\x00"
            WRAP_NATIVE = b"\x0b"
            UNWRAP_NATIVE = b"\x09"

            allowed_tokens = {k: v for k, v in tokens.items() if k in allowed_universal_symbols and v}

            commands = b""
            inputs = []
            value = 0
            deadline = int(time.time()) + 1800

            def encode_wrap(recipient: str, amount: int) -> bytes:
                # Universal Router WRAP_ETH: (address recipient, uint256 amountMinOut)
                return self.web3.codec.encode(
                    ['address', 'uint256'],
                    [Web3.to_checksum_address(recipient), amount]
                )

            def encode_unwrap(amount: int, recipient: str) -> bytes:
                # UNWRAP_ETH: (address recipient, uint256 amountMinOut)
                return self.web3.codec.encode(
                    ['address', 'uint256'],
                    [Web3.to_checksum_address(recipient), amount]
                )

            def encode_v3_swap(path: bytes, recipient: str, amount_in_v: int, min_out: int = 0) -> bytes:
                # V3_SWAP_EXACT_IN: (address recipient, uint256 amountIn, uint256 amountOutMin, bytes path)
                return self.web3.codec.encode(
                    ['address', 'uint256', 'uint256', 'bytes'],
                    [Web3.to_checksum_address(recipient), amount_in_v, min_out, path]
                )

            if native_to_token:
                native_targets = [sym for sym in ['SYN', 'USDT', 'WUSDC'] if sym in allowed_tokens]
                if not native_targets:
                    self.logger.error("❌ Universal router has no native->token targets configured")
                    return False
                target_symbol = from_symbol if from_symbol in native_targets else random.choice(native_targets)
                target_addr = tokens.get(target_symbol)

                commands = WRAP_NATIVE + V3_SWAP_EXACT_IN
                wrap_input = encode_wrap(wallet.address, amount_in)
                path = Web3.to_bytes(hexstr=wusdc_addr[2:]) + (3000).to_bytes(3, 'big') + Web3.to_bytes(
                    hexstr=target_addr[2:])
                swap_input = encode_v3_swap(path, wallet.address, amount_in, 0)
                inputs = [wrap_input, swap_input]
                value = amount_in
                token_for_log = target_addr
            else:
                # token -> native (USDC is chain native)
                if from_symbol not in allowed_tokens:
                    self.logger.error(f"❌ Universal router not allowed for token {from_symbol}")
                    return await arc_reroll()

                token_addr = tokens.get(from_symbol)
                if not token_addr:
                    self.logger.error(f"❌ Token address missing for {from_symbol}")
                    return False

                # WUSDC -> USDC is unwrap/withdraw on token contract, not a swap
                if from_symbol == 'WUSDC':
                    wusdc_contract = self.web3.eth.contract(
                        address=Web3.to_checksum_address(token_addr),
                        abi=self._get_wopn_abi()
                    )
                    gas_price = max(self.web3.eth.gas_price, self.web3.to_wei(5, 'gwei'))
                    tx = wusdc_contract.functions.withdraw(amount_in).build_transaction({
                        'from': wallet.address,
                        'value': 0,
                        'gas': 200000,
                        'gasPrice': gas_price,
                        'nonce': self.web3.eth.get_transaction_count(wallet.address),
                        'chainId': self.web3.eth.chain_id
                    })
                    self.logger.info(f"📤 Arc unwrap WUSDC -> USDC via withdraw, amount {await self._format_amount(amount_in, token_addr)}")
                    signed_txn = wallet.account.sign_transaction(tx)
                    tx_hash = self.web3.eth.send_raw_transaction(signed_txn.raw_transaction)
                    receipt = await asyncio.to_thread(
                        self.web3.eth.wait_for_transaction_receipt,
                        tx_hash,
                        timeout=240
                    )
                    if receipt.status == 1:
                        self.logger.info(f"✅ Arc WUSDC withdraw successful: {tx_hash.hex()}")
                        return True
                    self.logger.error("❌ Arc WUSDC withdraw reverted, attempting Curve fallback")
                    # fall through to Curve fallback logic below
                # generic allowed tokens -> native through Universal Router
                if not await self.approve_token(wallet, token_addr, amount_in):
                    return False

                commands = V3_SWAP_EXACT_IN + UNWRAP_NATIVE
                path = Web3.to_bytes(hexstr=token_addr[2:]) + (3000).to_bytes(3, 'big') + Web3.to_bytes(
                    hexstr=wusdc_addr[2:])
                swap_input = encode_v3_swap(path, wallet.address, amount_in, 0)
                unwrap_input = encode_unwrap(amount_in, wallet.address)
                inputs = [swap_input, unwrap_input]
                value = 0
                token_for_log = token_addr

            try:
                transaction = self.router_contract.functions.execute(
                    commands,
                    inputs,
                    deadline
                ).build_transaction({
                    'from': wallet.address,
                    'value': value,
                    'gas': 700000,
                    'gasPrice': gas_price,
                    'nonce': self.web3.eth.get_transaction_count(wallet.address),
                    'chainId': self.web3.eth.chain_id
                })

                self.logger.info(
                    f"📤 Arc swap via Universal Router | direction={'native->token' if native_to_token else 'token->native'} "
                    f"| from {from_symbol} amount {await self._format_amount(amount_in, token_for_log if not native_to_token else '0x0')}")

                signed_txn = wallet.account.sign_transaction(transaction)
                tx_hash = self.web3.eth.send_raw_transaction(signed_txn.raw_transaction)
                receipt = await asyncio.to_thread(
                    self.web3.eth.wait_for_transaction_receipt,
                    tx_hash,
                    timeout=240
                )

                if receipt.status == 1:
                    self.logger.info(f"✅ Arc Universal swap successful: {tx_hash.hex()}")
                    return True

                self.logger.error("❌ Arc swap failed (reverted), attempting Curve fallback")
            except Exception as e:
                self.logger.error(f"❌ Universal swap build/send failed: {e}, attempting Curve fallback")

            # Fallback: пробуем Curve, если не прошло
            templates = self._get_arc_route_templates(tokens)
            arc_tokens = list(templates.keys())
            if not arc_tokens or not self.arc_curve_router_contract:
                return False

            gas_price_retry = max(self.web3.eth.gas_price, int(gas_price * 1.1))

            # Пробуем тот же баланс/направление, но через Curve
            route_data = None
            target_symbol = native_symbol
            spendable = 0
            if native_to_token:
                allowed_forward = [t for t in arc_tokens if t not in curve_blacklist]
                if not allowed_forward:
                    return False
                target_symbol = random.choice(allowed_forward)
                route_data = templates.get(target_symbol, {}).get('forward')
                if not route_data:
                    return False

                balance_available = native_balance
                gas_reserve = wallet.web3.to_wei(0.05, 'ether')
                spendable = max(balance_available - gas_reserve, 0)
            else:
                # токен -> native: выберем токен с балансом в Curve списке
                candidates = [t for t in arc_tokens if t in nonzero_tokens]
                if not candidates:
                    return False
                from_symbol = random.choice(candidates)
                route_data = templates.get(from_symbol, {}).get('reverse')
                if not route_data:
                    return False
                from_address = tokens.get(from_symbol)
                spendable = nonzero_tokens.get(from_symbol, 0)

            if spendable <= 0:
                return False

            # Пересчитываем сумму под фактический баланс выбранного токена
            amount_in = int(spendable * swap_percentage)
            amount_in = await apply_min_amount(from_symbol, amount_in)
            if amount_in <= 0:
                amount_in = min(spendable, 1)
            if native_to_token and amount_in > spendable:
                amount_in = spendable

            if not native_to_token:
                from_address = tokens.get(from_symbol)
                if not await self.approve_token(wallet, from_address, amount_in):
                    return False

            zero_address = "0x0000000000000000000000000000000000000000"
            route = []
            for addr in route_data['route']:
                if addr.lower() == zero_address:
                    route.append(zero_address)
                else:
                    route.append(Web3.to_checksum_address(addr))
            swap_params = [list(map(int, row)) for row in route_data['swap_params']]

            transaction = self.arc_curve_router_contract.functions.exchange(
                route,
                swap_params,
                amount_in,
                0
            ).build_transaction({
                'from': wallet.address,
                'value': amount_in if native_to_token else 0,
                'gas': 700000,
                'gasPrice': gas_price_retry,
                'nonce': self.web3.eth.get_transaction_count(wallet.address),
                'chainId': self.web3.eth.chain_id
            })

            spent_readable = await self._format_amount(
                amount_in,
                zero_address if native_to_token else tokens.get(from_symbol)
            )
            self.logger.info(
                f"📤 Arc swap via Curve (fallback) {from_symbol} -> "
                f"{target_symbol if native_to_token else native_symbol}: {spent_readable}"
            )

            signed_txn = wallet.account.sign_transaction(transaction)
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.raw_transaction)
            receipt = await asyncio.to_thread(
                self.web3.eth.wait_for_transaction_receipt,
                tx_hash,
                timeout=240
            )
            if receipt.status == 1:
                self.logger.info(f"✅ Arc Curve fallback swap successful: {tx_hash.hex()}")
                return True

            self.logger.error("❌ Arc swap failed (fallback Curve reverted)")
            return await arc_reroll()

        except Exception as e:
            self.logger.error(f"❌ Arc swap failed: {e}")
            return await arc_reroll()

    async def _execute_opn_swap(self, wallet, normalized_network: str) -> bool:
        """SWAP/обертка для OPN Testnet (в обе стороны OPN <-> токены)"""
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

            balance_snapshot = await self._snapshot_token_balances(wallet, tokens)
            native_balance = balance_snapshot.get('__native__', 0)
            nonzero_tokens = {sym: bal for sym, bal in balance_snapshot.items() if sym != '__native__' and bal > 0}
            self.logger.debug(
                f"💰 Swap balance snapshot | native: {self.web3.from_wei(native_balance, 'ether'):.6f} "
                f"| tokens: {', '.join(nonzero_tokens.keys()) if nonzero_tokens else 'none'}")

            direction_roll = random.random()
            reverse_symbols = ['OPNT', 'WOPN', 'tUSDT', 'tBNB']
            reverse_candidates = {sym: bal for sym, bal in nonzero_tokens.items() if sym in reverse_symbols}

            has_native_for_swap = native_balance > 0
            has_tokens_for_swap = bool(reverse_candidates)

            if not has_native_for_swap and not has_tokens_for_swap:
                self.logger.warning("⚠️ No balance available for any OPN swap direction")
                return False

            # 50/50 между OPN->токены и токен->токен (включая OPN как цель)
            prefer_native_to_tokens = direction_roll < 0.5

            if prefer_native_to_tokens and has_native_for_swap:
                direction = "native_to_token"
            elif has_tokens_for_swap:
                direction = "token_to_token"
            elif has_native_for_swap:
                direction = "native_to_token"
            else:
                direction = "token_to_token"

            def _pick_amount(balance_raw: int, decimals: int, pct_range: tuple,
                             precision_options: list, max_spend: int = None) -> int:
                """Случайный процент с вариативной точностью"""
                pct = random.uniform(pct_range[0], pct_range[1])
                digits = random.choice(precision_options)
                amount_float = (balance_raw / (10 ** decimals)) * pct / 100
                amount_float = round(amount_float, digits)
                amount_raw = int(amount_float * (10 ** decimals))
                cap = max_spend if max_spend is not None else balance_raw
                amount_raw = min(amount_raw, cap)
                if amount_raw <= 0:
                    amount_raw = min(cap, 1)
                return amount_raw

            if direction == "native_to_token":
                gas_reserve = wallet.web3.to_wei(0.02, 'ether')
                spendable_balance = max(native_balance - gas_reserve, 0)
                if spendable_balance <= 0:
                    self.logger.warning("⚠️ Not enough balance to keep gas reserve on OPN")
                    return False

                # 3-7% от OPN с плавающей точностью
                amount_in = _pick_amount(
                    spendable_balance,
                    18,
                    (3.0, 7.0),
                    [3, 4, 5],
                    spendable_balance
                )
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

            # token -> token (включая OPN как цель)
            from_symbol, token_balance = random.choice(list(reverse_candidates.items()))
            token_address = tokens.get(from_symbol)
            if not token_address:
                self.logger.error(f"❌ Token address not configured for {from_symbol}")
                return False

            target_pool = [sym for sym in available_targets + ['OPN'] if sym != from_symbol]
            if from_symbol == 'WOPN':
                # Исключаем направление WOPN -> OPN
                target_pool = [sym for sym in target_pool if sym != 'OPN']
            if not target_pool:
                self.logger.warning("⚠️ No suitable target token for OPN token->token swap")
                return False
            target_symbol = random.choice(target_pool)

            decimals = await self.get_token_decimals(token_address)
            # 4-11% для токенов (не OPN) с рандомной точностью
            amount_in = _pick_amount(
                token_balance,
                decimals,
                (4.0, 11.0),
                [2, 3, 4, 5],
                token_balance
            )

            opn_balance_before = wallet.web3.eth.get_balance(wallet.address)
            gained_native = 0

            if from_symbol == 'WOPN':
                gas_price = max(self.web3.eth.gas_price, self.web3.to_wei(7, 'gwei'))
                wopn_contract = self.web3.eth.contract(
                    address=Web3.to_checksum_address(token_address),
                    abi=self._get_wopn_abi()
                )
                tx = wopn_contract.functions.withdraw(amount_in).build_transaction({
                    'from': wallet.address,
                    'value': 0,
                    'gas': 120000,
                    'gasPrice': gas_price,
                    'nonce': self.web3.eth.get_transaction_count(wallet.address),
                    'chainId': self.web3.eth.chain_id
                })

                self.logger.info(
                    f"📤 OPN unwrap WOPN -> OPN for token swap, amount: {await self._format_amount(amount_in, token_address)}"
                )
                signed_txn = wallet.account.sign_transaction(tx)
                tx_hash = self.web3.eth.send_raw_transaction(signed_txn.raw_transaction)
                receipt = await asyncio.to_thread(
                    self.web3.eth.wait_for_transaction_receipt,
                    tx_hash,
                    timeout=180
                )
                if receipt.status != 1:
                    self.logger.error("❌ WOPN unwrap failed")
                    return False

                self.logger.info(f"✅ Unwrapped WOPN to OPN: {tx_hash.hex()}")
                gained_native = amount_in
            else:
                if not await self.approve_token(wallet, token_address, amount_in):
                    return False

                deadline = self.web3.eth.get_block('latest')['timestamp'] + 1200
                gas_price = max(self.web3.eth.gas_price, self.web3.to_wei(7, 'gwei'))
                path = [
                    Web3.to_checksum_address(token_address),
                    Web3.to_checksum_address(wopn_address)
                ]

                transaction = self.router_contract.functions.swapExactTokensForOPN(
                    amount_in,
                    0,
                    path,
                    wallet.address,
                    deadline
                ).build_transaction({
                    'from': wallet.address,
                    'value': 0,
                    'gas': 500000,
                    'gasPrice': gas_price,
                    'nonce': self.web3.eth.get_transaction_count(wallet.address),
                    'chainId': self.web3.eth.chain_id
                })

                self.logger.info(
                    f"📤 OPN swap token->OPN for routing: {from_symbol} amount {amount_in / (10 ** decimals):.6f} -> OPN"
                )

                signed_txn = wallet.account.sign_transaction(transaction)
                tx_hash = self.web3.eth.send_raw_transaction(signed_txn.raw_transaction)
                receipt = await asyncio.to_thread(
                    self.web3.eth.wait_for_transaction_receipt,
                    tx_hash,
                    timeout=180
                )

                if receipt.status != 1:
                    self.logger.error("❌ swapExactTokensForOPN reverted")
                    return False

                opn_balance_after = wallet.web3.eth.get_balance(wallet.address)
                gained_native = max(opn_balance_after - opn_balance_before, 0)
                self.logger.info(
                    f"✅ OPN swap successful: {tx_hash.hex()} | {from_symbol} -> OPN, received ~{await self._format_amount(gained_native or amount_in, '0x0000000000000000000000000000000000000000')} OPN"
                )

            if target_symbol == 'OPN':
                return True

            gas_reserve = wallet.web3.to_wei(0.02, 'ether')
            spendable_native = max(gained_native - gas_reserve, 0)
            if spendable_native <= 0:
                self.logger.warning("⚠️ Not enough OPN after first leg to proceed with token swap")
                return False

            # Вторая нога: OPN -> целевой токен
            if target_symbol == 'WOPN':
                return await self._wrap_opn_to_wopn(wallet, wopn_address, spendable_native)

            target_address = tokens.get(target_symbol)
            if not target_address:
                self.logger.error(f"❌ Target token address not configured for {target_symbol}")
                return False

            return await self._perform_opn_swap(wallet, spendable_native, wopn_address, target_address, target_symbol)

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
