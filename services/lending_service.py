import asyncio
import random
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Optional

from web3 import Web3

from config.constants import is_pharos_network, normalize_network_name
from utils.logger import setup_logger


class LendingService:
    SUPPLY_SELECTOR = "0x617ba037"
    BORROW_SELECTOR = "0xa415bcad"
    MAX_ALLOWANCE = 2**256 - 1
    APPROVE_GAS_LIMIT = 120000
    SUPPLY_GAS_LIMIT = 300000
    BORROW_GAS_LIMIT = 350000
    MIN_NATIVE_WEI = Web3.to_wei(0.001, "ether")
    DEFAULT_LENDING_POOL = "0x62e72185f7deabda9f6a3df3b23d67530b42eff6"
    VARIABLE_INTEREST_MODE = 2

    def __init__(self, web3_instance, config):
        self.web3 = web3_instance
        self.config = config
        self.logger = getattr(config, "logger", setup_logger("LendingService"))

        self.erc20_abi = [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function",
            },
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "type": "function",
            },
            {
                "constant": True,
                "inputs": [
                    {"name": "_owner", "type": "address"},
                    {"name": "_spender", "type": "address"},
                ],
                "name": "allowance",
                "outputs": [{"name": "", "type": "uint256"}],
                "type": "function",
            },
            {
                "constant": False,
                "inputs": [
                    {"name": "_spender", "type": "address"},
                    {"name": "_value", "type": "uint256"},
                ],
                "name": "approve",
                "outputs": [{"name": "", "type": "bool"}],
                "type": "function",
            },
        ]

        self.lending_abi = [
            {
                "inputs": [
                    {"internalType": "address", "name": "asset", "type": "address"},
                    {"internalType": "uint256", "name": "amount", "type": "uint256"},
                    {"internalType": "address", "name": "onBehalfOf", "type": "address"},
                    {"internalType": "uint16", "name": "referralCode", "type": "uint16"},
                ],
                "name": "supply",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function",
            },
            {
                "inputs": [
                    {"internalType": "address", "name": "asset", "type": "address"},
                    {"internalType": "uint256", "name": "amount", "type": "uint256"},
                    {"internalType": "uint256", "name": "interestRateMode", "type": "uint256"},
                    {"internalType": "uint16", "name": "referralCode", "type": "uint16"},
                    {"internalType": "address", "name": "onBehalfOf", "type": "address"},
                ],
                "name": "borrow",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function",
            }
        ]

        self.token_ranges = self._build_token_ranges()
        self.borrow_ranges = self._build_borrow_ranges()
        self.lending_pool_address = self._get_lending_pool_address()
        self.lending_contract = (
            self.web3.eth.contract(
                address=self.web3.to_checksum_address(self.lending_pool_address),
                abi=self.lending_abi,
            )
            if self.lending_pool_address and self.web3
            else None
        )

    def _build_token_ranges(self) -> Dict[str, Dict]:
        """Конфигурация токенов для lending на Pharos."""
        pharos_config = self.config.get_pharos_config() if self.config else None
        tokens = pharos_config.get("tokens", {}) if pharos_config else {}

        ranges = {
            "WBTC": {
                "address": tokens.get("WBTC"),
                "min": Decimal("0.00015"),
                "max": Decimal("0.0015"),
            },
            "WETH": {
                "address": tokens.get("WETH"),
                "min": Decimal("0.0035"),
                "max": Decimal("0.04"),
            },
        }

        # Приводим адреса к checksum и отбрасываем отсутствующие токены
        prepared = {}
        for symbol, data in ranges.items():
            addr = data.get("address")
            if not addr:
                continue
            try:
                prepared[symbol] = {
                    "address": Web3.to_checksum_address(addr),
                    "min": data["min"],
                    "max": data["max"],
                    "decimals": None,
                }
            except Exception:
                continue
        return prepared

    def _build_borrow_ranges(self) -> Dict[str, Dict]:
        ranges = {
            "WBTC": {"min": Decimal("0.00005"), "max": Decimal("0.0002")},
            "WETH": {"min": Decimal("0.0009"), "max": Decimal("0.0065")},
        }
        return ranges

    def _get_lending_pool_address(self) -> Optional[str]:
        try:
            pharos_config = self.config.get_pharos_config() if self.config else None
            contract_addr = None
            if pharos_config:
                contract_addr = (
                    pharos_config.get("contracts", {}).get("lending_pool")
                    or pharos_config.get("contracts", {}).get("structure_subscription")
                )
            return Web3.to_checksum_address(contract_addr or self.DEFAULT_LENDING_POOL)
        except Exception:
            return None

    def _get_explorer_link(self, tx_hash: str) -> Optional[str]:
        pharos_config = self.config.get_pharos_config() if self.config else None
        explorer = pharos_config.get("explorer") if pharos_config else None
        if explorer:
            return f"{explorer.rstrip('/')}/tx/{tx_hash}"
        return None

    def _get_token_decimals(self, token_address: str) -> int:
        try:
            contract = self.web3.eth.contract(address=token_address, abi=self.erc20_abi)
            return contract.functions.decimals().call()
        except Exception:
            return 18

    async def _get_token_balance(self, wallet, token_address: str, decimals: int) -> Decimal:
        try:
            contract = self.web3.eth.contract(address=token_address, abi=self.erc20_abi)
            raw = contract.functions.balanceOf(wallet.address).call()
            return Decimal(raw) / (Decimal(10) ** decimals)
        except Exception as exc:
            self.logger.error(f"{wallet.name}: failed to fetch token balance: {exc}")
            return Decimal("0")

    def _to_wei(self, amount: Decimal, decimals: int) -> int:
        scale = Decimal(10) ** decimals
        return int((amount * scale).to_integral_value(rounding=ROUND_DOWN))

    def _choose_amount(self, min_amount: Decimal, max_amount: Decimal, balance: Decimal) -> Optional[Decimal]:
        upper = min(max_amount, balance)
        if upper < min_amount:
            return None

        raw = Decimal(random.uniform(float(min_amount), float(upper)))
        return raw.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)

    async def _ensure_allowance(self, wallet, token_address: str, amount_wei: int) -> bool:
        try:
            contract = self.web3.eth.contract(address=token_address, abi=self.erc20_abi)
            allowance = contract.functions.allowance(wallet.address, self.lending_pool_address).call()
            if allowance >= amount_wei:
                return True

            nonce = self.web3.eth.get_transaction_count(wallet.address)
            gas_price = self.web3.eth.gas_price
            tx = contract.functions.approve(self.lending_pool_address, self.MAX_ALLOWANCE).build_transaction(
                {
                    "from": wallet.address,
                    "gas": self.APPROVE_GAS_LIMIT,
                    "maxFeePerGas": gas_price,
                    "maxPriorityFeePerGas": gas_price,
                    "nonce": nonce,
                    "chainId": self.web3.eth.chain_id,
                }
            )

            signed = wallet.account.sign_transaction(tx)
            tx_hash = self.web3.eth.send_raw_transaction(signed.raw_transaction)
            self.logger.info(f"{wallet.name}: approving {token_address} for lending pool")

            receipt = await asyncio.to_thread(
                self.web3.eth.wait_for_transaction_receipt, tx_hash, timeout=240
            )
            if receipt.status == 1:
                return True

            self.logger.error(f"{wallet.name}: approve failed with status {receipt.status}")
            return False

        except Exception as exc:
            self.logger.error(f"{wallet.name}: approve error: {exc}")
            return False

    async def _supply(self, wallet, token_symbol: str, token_address: str, amount_wei: int, human_amount: Decimal) -> bool:
        try:
            nonce = self.web3.eth.get_transaction_count(wallet.address)
            gas_price = self.web3.eth.gas_price
            tx = self.lending_contract.functions.supply(
                token_address,
                amount_wei,
                wallet.address,
                0,
            ).build_transaction(
                {
                    "from": wallet.address,
                    "gas": self.SUPPLY_GAS_LIMIT,
                    "maxFeePerGas": gas_price,
                    "maxPriorityFeePerGas": gas_price,
                    "nonce": nonce,
                    "chainId": self.web3.eth.chain_id,
                }
            )

            signed = wallet.account.sign_transaction(tx)
            tx_hash = self.web3.eth.send_raw_transaction(signed.raw_transaction)
            self.logger.info(f"{wallet.name}: supplying {human_amount} {token_symbol} to lending pool")

            receipt = await asyncio.to_thread(
                self.web3.eth.wait_for_transaction_receipt, tx_hash, timeout=240
            )
            if receipt.status == 1:
                explorer = self._get_explorer_link(tx_hash.hex())
                if explorer:
                    self.logger.info(f"{wallet.name}: lending confirmed {explorer}")
                return True

            self.logger.error(f"{wallet.name}: lending failed with status {receipt.status}")
            return False

        except Exception as exc:
            self.logger.error(f"{wallet.name}: supply error for {token_symbol}: {exc}")
            return False

    async def _borrow(self, wallet, token_symbol: str, token_address: str, amount_wei: int, human_amount: Decimal) -> bool:
        try:
            nonce = self.web3.eth.get_transaction_count(wallet.address)
            gas_price = self.web3.eth.gas_price
            tx = self.lending_contract.functions.borrow(
                token_address,
                amount_wei,
                self.VARIABLE_INTEREST_MODE,
                0,
                wallet.address,
            ).build_transaction(
                {
                    "from": wallet.address,
                    "gas": self.BORROW_GAS_LIMIT,
                    "maxFeePerGas": gas_price,
                    "maxPriorityFeePerGas": gas_price,
                    "nonce": nonce,
                    "chainId": self.web3.eth.chain_id,
                }
            )

            signed = wallet.account.sign_transaction(tx)
            tx_hash = self.web3.eth.send_raw_transaction(signed.raw_transaction)
            self.logger.info(f"{wallet.name}: borrowing {human_amount} {token_symbol} from lending pool")

            receipt = await asyncio.to_thread(
                self.web3.eth.wait_for_transaction_receipt, tx_hash, timeout=240
            )
            if receipt.status == 1:
                explorer = self._get_explorer_link(tx_hash.hex())
                if explorer:
                    self.logger.info(f"{wallet.name}: borrow confirmed {explorer}")
                return True

            self.logger.error(f"{wallet.name}: borrow failed with status {receipt.status}")
            return False

        except Exception as exc:
            self.logger.error(f"{wallet.name}: borrow error for {token_symbol}: {exc}")
            return False

    async def execute_lend(self, wallet, network_name: Optional[str] = None) -> bool:
        """Поставка ликвидности (lending) в сети Pharos Atlantic через supply()."""
        try:
            if not self.web3 or not self.web3.is_connected():
                self.logger.error("❌ Web3 not connected for lending")
                return False

            # Проверяем, что это Pharos Atlantic
            resolved_network = network_name
            if not resolved_network and self.config:
                network_cfg = self.config.get_network_by_chain_id(self.web3.eth.chain_id)
                resolved_network = network_cfg.get("name") if network_cfg else None

            normalized = normalize_network_name(resolved_network) if resolved_network else ""
            if not is_pharos_network(normalized):
                self.logger.info(f"ℹ️ Lending is only enabled for Pharos Atlantic (got '{normalized}')")
                return False

            if not self.lending_contract or not self.lending_pool_address:
                self.logger.error("❌ Lending pool contract is not configured")
                return False

            native_balance = self.web3.eth.get_balance(wallet.address)
            if native_balance < self.MIN_NATIVE_WEI:
                human_native = self.web3.from_wei(native_balance, "ether")
                self.logger.info(f"{wallet.name}: low native balance {human_native:.6f}, need at least 0.001 for gas")
                return False

            # Подготовка токенов с актуальными балансами
            available_tokens = []
            for symbol, data in self.token_ranges.items():
                decimals = data["decimals"] or self._get_token_decimals(data["address"])
                self.token_ranges[symbol]["decimals"] = decimals

                balance = await self._get_token_balance(wallet, data["address"], decimals)
                if balance <= Decimal("0"):
                    self.logger.info(f"{wallet.name}: no {symbol} balance, skipping")
                    continue

                if balance < data["min"]:
                    self.logger.info(f"{wallet.name}: {symbol} balance {balance:.8f} below minimum {data['min']}")
                    continue

                available_tokens.append((symbol, data, balance, decimals))

            if not available_tokens:
                self.logger.info(f"{wallet.name}: no eligible tokens for lending")
                return False

            token_symbol, token_data, balance, decimals = random.choice(available_tokens)
            amount = self._choose_amount(token_data["min"], token_data["max"], balance)
            if amount is None:
                self.logger.info(f"{wallet.name}: insufficient {token_symbol} balance for lending")
                return False

            amount_wei = self._to_wei(amount, decimals)
            if amount_wei <= 0:
                self.logger.warning(f"{wallet.name}: calculated lend amount is zero")
                return False

            self.logger.info(
                f"{wallet.name}: preparing to lend {amount} {token_symbol} "
                f"(balance {balance:.8f}, decimals {decimals})"
            )

            if not await self._ensure_allowance(wallet, token_data["address"], amount_wei):
                return False

            return await self._supply(wallet, token_symbol, token_data["address"], amount_wei, amount)

        except Exception as e:
            self.logger.error(f"❌ Lend operation failed for {wallet.name}: {e}")
            return False

    async def execute_borrow(self, wallet, network_name: Optional[str] = None) -> bool:
        """Заём ликвидности (borrow) в сети Pharos Atlantic."""
        try:
            if not self.web3 or not self.web3.is_connected():
                self.logger.error("❌ Web3 not connected for borrowing")
                return False

            resolved_network = network_name
            if not resolved_network and self.config:
                network_cfg = self.config.get_network_by_chain_id(self.web3.eth.chain_id)
                resolved_network = network_cfg.get("name") if network_cfg else None

            normalized = normalize_network_name(resolved_network) if resolved_network else ""
            if not is_pharos_network(normalized):
                self.logger.info(f"ℹ️ Borrow is only enabled for Pharos Atlantic (got '{normalized}')")
                return False

            if not self.lending_contract or not self.lending_pool_address:
                self.logger.error("❌ Lending pool contract is not configured")
                return False

            native_balance = self.web3.eth.get_balance(wallet.address)
            if native_balance < self.MIN_NATIVE_WEI:
                human_native = self.web3.from_wei(native_balance, "ether")
                self.logger.info(f"{wallet.name}: low native balance {human_native:.6f}, need at least 0.001 for gas")
                return False

            borrow_candidates = []
            for symbol, data in self.token_ranges.items():
                if symbol not in self.borrow_ranges:
                    continue

                decimals = data["decimals"] or self._get_token_decimals(data["address"])
                self.token_ranges[symbol]["decimals"] = decimals
                borrow_candidates.append((symbol, data, decimals, self.borrow_ranges[symbol]))

            if not borrow_candidates:
                self.logger.info(f"{wallet.name}: no eligible tokens for borrowing")
                return False

            token_symbol, token_data, decimals, borrow_range = random.choice(borrow_candidates)
            amount = self._choose_amount(borrow_range["min"], borrow_range["max"], borrow_range["max"])
            if amount is None:
                self.logger.info(f"{wallet.name}: unable to pick borrow amount for {token_symbol}")
                return False

            amount_wei = self._to_wei(amount, decimals)
            if amount_wei <= 0:
                self.logger.warning(f"{wallet.name}: calculated borrow amount is zero")
                return False

            self.logger.info(
                f"{wallet.name}: preparing to borrow {amount} {token_symbol} "
                f"(decimals {decimals}, mode variable)"
            )

            return await self._borrow(wallet, token_symbol, token_data["address"], amount_wei, amount)

        except Exception as e:
            self.logger.error(f"❌ Borrow operation failed for {wallet.name}: {e}")
            return False
