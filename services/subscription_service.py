import asyncio
import random
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, getcontext
from typing import List, Optional, Tuple

from web3 import Web3

from config.constants import is_pharos_network, normalize_network_name
from utils.logger import setup_logger

# Higher precision is useful when converting token amounts to wei
getcontext().prec = 36


@dataclass
class SubscriptionAsset:
    name: str
    symbol: str
    token_address: str
    asset_id: str
    decimals: int = 18
    min_amount: float = 0.0
    max_amount: float = 0.0


class SubscriptionService:
    SUBSCRIBE_SELECTOR = "0xef272020"  # subscribe(bytes32,uint256)
    MAX_ALLOWANCE = 2 ** 256 - 1

    def __init__(self, web3_instance, config, gas_monitor=None):
        self.web3 = web3_instance
        self.config = config
        self.gas_monitor = gas_monitor
        self.logger = setup_logger("SubscriptionService")

        self.subscription_settings = self.config.get_subscription_settings()
        self.subscription_contract = self._get_subscription_contract()
        self.assets: List[SubscriptionAsset] = self._load_assets()

        self.erc20_abi = self._erc20_abi()
        self.wallet_transaction_count = {}

    @staticmethod
    def _erc20_abi():
        return [
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
                "inputs": [],
                "name": "symbol",
                "outputs": [{"name": "", "type": "string"}],
                "type": "function",
            },
            {
                "constant": False,
                "inputs": [
                    {"name": "_spender", "type": "address"},
                    {"name": "_value", "type": "uint256"},
                ],
                "name": "approve",
                "outputs": [{"name": "success", "type": "bool"}],
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
        ]

    def _get_subscription_contract(self) -> Optional[str]:
        """Locate subscription contract address from settings or network contracts."""
        direct = self.subscription_settings.get("contract_address")
        if direct:
            return Web3.to_checksum_address(direct)

        pharos = self.config.get_network_by_name("Pharos Atlantic")
        if pharos and "contracts" in pharos:
            addr = pharos["contracts"].get("structure_subscription")
            if addr:
                return Web3.to_checksum_address(addr)

        self.logger.error("No subscription contract address configured for Pharos Atlantic")
        return None

    def _load_assets(self) -> List[SubscriptionAsset]:
        """Load subscription assets from config and normalise addresses."""
        assets_config = self.subscription_settings.get("assets", [])
        assets: List[SubscriptionAsset] = []

        for raw in assets_config:
            try:
                asset_id = raw.get("asset_id")
                token_address = raw.get("token_address")
                if not asset_id or not token_address:
                    continue

                name = raw.get("name", "Unknown")
                symbol = raw.get("symbol", "")
                decimals = raw.get("decimals", 18)
                min_amount = float(raw.get("min_amount", 0))
                max_amount = float(raw.get("max_amount", 0))

                checksum_token = Web3.to_checksum_address(token_address)
                asset_id_hex = asset_id if asset_id.startswith("0x") else f"0x{asset_id}"

                assets.append(
                    SubscriptionAsset(
                        name=name,
                        symbol=symbol,
                        token_address=checksum_token,
                        asset_id=asset_id_hex,
                        decimals=decimals,
                        min_amount=min_amount,
                        max_amount=max_amount,
                    )
                )
            except Exception as exc:
                self.logger.error(f"Failed to load asset config {raw}: {exc}")

        if not assets:
            self.logger.error("No subscription assets configured")
        return assets

    async def get_wallet_transaction_count(self, wallet_address: str) -> int:
        """Return known transaction count for the wallet (on-chain or tracked)."""
        try:
            onchain = self.web3.eth.get_transaction_count(wallet_address)
            tracked = self.wallet_transaction_count.get(wallet_address.lower(), 0)
            return max(onchain, tracked)
        except Exception as exc:
            self.logger.error(f"Error reading nonce for {wallet_address}: {exc}")
            return self.wallet_transaction_count.get(wallet_address.lower(), 0)

    def _increment_wallet_transaction_count(self, wallet_address: str):
        key = wallet_address.lower()
        current = self.wallet_transaction_count.get(key, 0)
        self.wallet_transaction_count[key] = current + 1

    async def check_transaction_limit(self, wallet, max_transactions: int) -> bool:
        try:
            count = await self.get_wallet_transaction_count(wallet.address)
            if count >= max_transactions:
                self.logger.warning(
                    f"Skipping {wallet.name}: transaction limit reached {count}/{max_transactions}"
                )
                return False
            return True
        except Exception as exc:
            self.logger.error(f"Transaction limit check failed for {wallet.name}: {exc}")
            return True

    def _to_wei(self, amount: float, decimals: int) -> int:
        quantized = Decimal(str(amount)).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
        wei_value = quantized * (Decimal(10) ** decimals)
        return int(wei_value.to_integral_value(rounding=ROUND_DOWN))

    async def _get_token_decimals(self, asset: SubscriptionAsset) -> int:
        if asset.decimals:
            return asset.decimals
        try:
            contract = self.web3.eth.contract(address=asset.token_address, abi=self.erc20_abi)
            decimals = contract.functions.decimals().call()
            asset.decimals = decimals
            return decimals
        except Exception as exc:
            self.logger.error(f"Failed to fetch decimals for {asset.symbol}: {exc}")
            return 18

    async def _get_token_balance(
        self, wallet, asset: SubscriptionAsset, decimals: int
    ) -> Tuple[float, int]:
        try:
            contract = self.web3.eth.contract(address=asset.token_address, abi=self.erc20_abi)
            raw_balance = contract.functions.balanceOf(wallet.address).call()
            readable = raw_balance / (10 ** decimals)
            return float(readable), raw_balance
        except Exception as exc:
            self.logger.error(f"Failed to fetch balance for {asset.symbol}: {exc}")
            return 0.0, 0

    def _choose_amount(self, asset: SubscriptionAsset, balance: float) -> Optional[float]:
        pct_cap = self.subscription_settings.get("max_percentage_of_balance", 100)
        max_by_balance = balance * (pct_cap / 100)
        upper = min(asset.max_amount, max_by_balance)
        lower = asset.min_amount

        if upper <= 0 or upper < lower:
            return None

        # Randomize precision between 0.1 and 0.001
        precision = random.choice([Decimal("0.1"), Decimal("0.01"), Decimal("0.001")])
        amount = Decimal(random.uniform(lower, upper)).quantize(precision, rounding=ROUND_DOWN)
        if amount <= 0:
            return None
        return float(amount)

    async def _ensure_allowance(
        self, wallet, asset: SubscriptionAsset, amount_wei: int
    ) -> bool:
        try:
            contract = self.web3.eth.contract(address=asset.token_address, abi=self.erc20_abi)
            allowance = contract.functions.allowance(wallet.address, self.subscription_contract).call()
            if allowance >= amount_wei:
                return True

            nonce = self.web3.eth.get_transaction_count(wallet.address)
            gas_limit = self.subscription_settings.get("approve_gas_limit", 120000)
            gas_price = self.web3.eth.gas_price

            tx = contract.functions.approve(
                self.subscription_contract, self.MAX_ALLOWANCE
            ).build_transaction(
                {
                    "from": wallet.address,
                    "gas": gas_limit,
                    "maxFeePerGas": gas_price,
                    "maxPriorityFeePerGas": gas_price,
                    "nonce": nonce,
                    "chainId": self.web3.eth.chain_id,
                }
            )

            signed = wallet.account.sign_transaction(tx)
            tx_hash = self.web3.eth.send_raw_transaction(signed.raw_transaction)
            self.logger.info(f"{wallet.name}: approval sent for {asset.symbol} ({tx_hash.hex()})")

            receipt = await asyncio.to_thread(
                self.web3.eth.wait_for_transaction_receipt, tx_hash, timeout=180
            )
            if receipt.status == 1:
                self._increment_wallet_transaction_count(wallet.address)
                return True

            self.logger.error(f"{wallet.name}: approval failed with status {receipt.status}")
            return False

        except Exception as exc:
            self.logger.error(f"{wallet.name}: approval error for {asset.symbol}: {exc}")
            return False

    def _encode_subscription_call(self, asset_id: str, amount_wei: int) -> str:
        selector = bytes.fromhex(self.SUBSCRIBE_SELECTOR.removeprefix("0x"))
        asset_bytes = bytes.fromhex(asset_id.removeprefix("0x")).rjust(32, b"\x00")
        amount_bytes = amount_wei.to_bytes(32, byteorder="big")
        return Web3.to_hex(selector + asset_bytes + amount_bytes)

    async def _execute_subscription(
        self, wallet, asset: SubscriptionAsset, amount_wei: int, human_amount: float
    ) -> bool:
        try:
            nonce = self.web3.eth.get_transaction_count(wallet.address)
            gas_limit = self.subscription_settings.get("subscribe_gas_limit", 450000)
            gas_price = self.web3.eth.gas_price

            tx = {
                "to": self.subscription_contract,
                "from": wallet.address,
                "value": 0,
                "data": self._encode_subscription_call(asset.asset_id, amount_wei),
                "gas": gas_limit,
                "maxFeePerGas": gas_price,
                "maxPriorityFeePerGas": gas_price,
                "nonce": nonce,
                "chainId": self.web3.eth.chain_id,
            }

            signed = wallet.account.sign_transaction(tx)
            tx_hash = self.web3.eth.send_raw_transaction(signed.raw_transaction)
            self.logger.info(
                f"{wallet.name}: subscribing {human_amount} {asset.symbol} via {self.subscription_contract}"
            )

            receipt = await asyncio.to_thread(
                self.web3.eth.wait_for_transaction_receipt, tx_hash, timeout=240
            )
            if receipt.status == 1:
                self._increment_wallet_transaction_count(wallet.address)
                explorer = self._build_explorer_link(tx_hash.hex())
                if explorer:
                    self.logger.info(f"{wallet.name}: subscription confirmed {explorer}")
                return True

            self.logger.error(f"{wallet.name}: subscription failed with status {receipt.status}")
            return False

        except Exception as exc:
            self.logger.error(f"{wallet.name}: subscription error for {asset.symbol}: {exc}")
            return False

    def _build_explorer_link(self, tx_hash: str) -> Optional[str]:
        network = self.config.get_network_by_name("Pharos Atlantic")
        explorer = network.get("explorer") if network else None
        if explorer:
            return f"{explorer.rstrip('/')}/tx/{tx_hash}"
        return None

    async def execute_random_subscription(self, wallet, network_name: str) -> bool:
        normalized = normalize_network_name(network_name)
        if not is_pharos_network(normalized):
            self.logger.info("Subscription flow is only enabled for Pharos Atlantic")
            return False

        if not self.subscription_contract or not self.assets:
            return False

        if not self.web3.is_connected():
            self.logger.error("Web3 provider is not connected")
            return False

        native_balance = self.web3.from_wei(self.web3.eth.get_balance(wallet.address), "ether")
        min_native = self.subscription_settings.get("min_native_balance", 0.001)
        if native_balance < min_native:
            self.logger.info(
                f"{wallet.name}: low native balance {native_balance:.6f}, needs at least {min_native}"
            )
            return False

        asset = random.choice(self.assets)
        decimals = await self._get_token_decimals(asset)
        balance_readable, _ = await self._get_token_balance(wallet, asset, decimals)
        if balance_readable <= 0:
            self.logger.info(f"{wallet.name}: no balance for {asset.symbol}, skipping")
            return False

        amount = self._choose_amount(asset, balance_readable)
        if amount is None or amount <= 0:
            self.logger.info(
                f"{wallet.name}: insufficient {asset.symbol} balance for subscription "
                f"(balance {balance_readable:.6f}, requires > {asset.min_amount})"
            )
            return False

        amount_wei = self._to_wei(amount, decimals)
        if not await self._ensure_allowance(wallet, asset, amount_wei):
            return False

        return await self._execute_subscription(wallet, asset, amount_wei, amount)

    def get_wallet_stats(self) -> dict:
        return self.wallet_transaction_count.copy()
