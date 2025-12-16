import asyncio
import random
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import List, Optional

from web3 import Web3

from config.constants import is_pharos_network, normalize_network_name


@dataclass
class StakingPool:
    name: str
    contract: str
    stake_token: str
    decimals: int = 18


class StakingService:
    STAKE_SELECTOR = "0xa694fc3a"
    MAX_ALLOWANCE = 2**256 - 1
    APPROVE_GAS_LIMIT = 120000
    STAKE_GAS_LIMIT = 220000

    def __init__(self, web3_instance, config):
        self.web3 = web3_instance
        self.config = config
        self.logger = config.logger
        self.pools: List[StakingPool] = [
            StakingPool(
                name="Stake Type 1",
                contract=Web3.to_checksum_address("0x534966536969c3B697A04538e475992C981521cF"),
                stake_token=Web3.to_checksum_address("0xEd75C5b68284A1a9568e26A2b48655A3D518D4bc"),
            ),
            StakingPool(
                name="Stake Type 2",
                contract=Web3.to_checksum_address("0x92864F94020e79A52aCA036c6A3d3be9D4388a39"),
                stake_token=Web3.to_checksum_address("0x93BC7267D802201e51926BEf331de80C965EC55F"),
            ),
            StakingPool(
                name="Stake Type 3",
                contract=Web3.to_checksum_address("0x3eaEf8F467059915a6EEb985a0d08dE063ab16F9"),
                stake_token=Web3.to_checksum_address("0xC1cF3cF3A86807e8319C0AB1754413c854aB5B7D"),
            ),
        ]
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

    def _encode_stake_call(self, amount_wei: int) -> str:
        selector = bytes.fromhex(self.STAKE_SELECTOR.removeprefix("0x"))
        amount_bytes = amount_wei.to_bytes(32, byteorder="big")
        return Web3.to_hex(selector + amount_bytes)

    def _build_explorer_link(self, tx_hash: str) -> Optional[str]:
        network = self.config.get_network_by_name("Pharos Atlantic")
        explorer = network.get("explorer") if network else None
        if explorer:
            return f"{explorer.rstrip('/')}/tx/{tx_hash}"
        return None

    def _get_decimals(self, pool: StakingPool) -> int:
        try:
            contract = self.web3.eth.contract(address=pool.stake_token, abi=self.erc20_abi)
            return contract.functions.decimals().call()
        except Exception:
            return pool.decimals

    def _to_wei(self, amount: Decimal, decimals: int) -> int:
        scale = Decimal(10) ** decimals
        return int((amount * scale).to_integral_value(rounding=ROUND_DOWN))

    def _choose_amount(self, balance: float) -> Optional[Decimal]:
        lower = Decimal("45")
        upper = min(Decimal("89"), Decimal(str(balance)))
        if upper < lower:
            return None

        precision = random.choice([Decimal("0.1"), Decimal("0.01"), Decimal("0.001")])
        amount = Decimal(random.uniform(float(lower), float(upper))).quantize(precision, rounding=ROUND_DOWN)
        return amount if amount > 0 else None

    async def _get_token_balance(self, wallet, pool: StakingPool, decimals: int) -> float:
        try:
            contract = self.web3.eth.contract(address=pool.stake_token, abi=self.erc20_abi)
            raw_balance = contract.functions.balanceOf(wallet.address).call()
            return raw_balance / (10 ** decimals)
        except Exception as exc:
            self.logger.error(f"{wallet.name}: failed to fetch balance for {pool.name}: {exc}")
            return 0.0

    async def _ensure_allowance(self, wallet, pool: StakingPool, amount_wei: int) -> bool:
        try:
            contract = self.web3.eth.contract(address=pool.stake_token, abi=self.erc20_abi)
            allowance = contract.functions.allowance(wallet.address, pool.contract).call()
            if allowance >= amount_wei:
                return True

            nonce = self.web3.eth.get_transaction_count(wallet.address)
            gas_price = self.web3.eth.gas_price
            tx = contract.functions.approve(pool.contract, self.MAX_ALLOWANCE).build_transaction(
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
            self.logger.info(f"{wallet.name}: approving {pool.stake_token} for {pool.name}")

            receipt = await asyncio.to_thread(
                self.web3.eth.wait_for_transaction_receipt, tx_hash, timeout=240
            )
            if receipt.status == 1:
                return True

            self.logger.error(f"{wallet.name}: approve failed with status {receipt.status}")
            return False

        except Exception as exc:
            self.logger.error(f"{wallet.name}: approve error for {pool.name}: {exc}")
            return False

    async def _execute_stake(
        self, wallet, pool: StakingPool, amount_wei: int, human_amount: Decimal
    ) -> bool:
        try:
            nonce = self.web3.eth.get_transaction_count(wallet.address)
            gas_price = self.web3.eth.gas_price
            tx = {
                "to": pool.contract,
                "from": wallet.address,
                "value": 0,
                "data": self._encode_stake_call(amount_wei),
                "gas": self.STAKE_GAS_LIMIT,
                "maxFeePerGas": gas_price,
                "maxPriorityFeePerGas": gas_price,
                "nonce": nonce,
                "chainId": self.web3.eth.chain_id,
            }

            signed = wallet.account.sign_transaction(tx)
            tx_hash = self.web3.eth.send_raw_transaction(signed.raw_transaction)
            self.logger.info(f"{wallet.name}: staking {human_amount} via {pool.name} ({pool.contract})")

            receipt = await asyncio.to_thread(
                self.web3.eth.wait_for_transaction_receipt, tx_hash, timeout=240
            )
            if receipt.status == 1:
                explorer = self._build_explorer_link(tx_hash.hex())
                if explorer:
                    self.logger.info(f"{wallet.name}: stake confirmed {explorer}")
                return True

            self.logger.error(f"{wallet.name}: stake failed with status {receipt.status}")
            return False

        except Exception as exc:
            self.logger.error(f"{wallet.name}: stake error for {pool.name}: {exc}")
            return False

    async def execute_random_stake(self, wallet, network_name: str) -> bool:
        normalized = normalize_network_name(network_name)
        if not is_pharos_network(normalized):
            self.logger.info("Staking is only enabled for Pharos Atlantic")
            return False

        if not self.web3.is_connected():
            self.logger.error("Web3 provider is not connected")
            return False

        native_balance = self.web3.from_wei(self.web3.eth.get_balance(wallet.address), "ether")
        if native_balance < 0.001:
            self.logger.info(f"{wallet.name}: low native balance {native_balance:.6f}, need at least 0.001")
            return False

        pool = random.choice(self.pools)
        decimals = self._get_decimals(pool)

        balance = await self._get_token_balance(wallet, pool, decimals)
        if balance <= 0:
            self.logger.info(f"{wallet.name}: no balance for staking token in {pool.name}, skipping")
            return False

        amount = self._choose_amount(balance)
        if amount is None:
            self.logger.info(f"{wallet.name}: insufficient balance ({balance:.6f}) for {pool.name}")
            return False

        amount_wei = self._to_wei(amount, decimals)
        if not await self._ensure_allowance(wallet, pool, amount_wei):
            return False

        return await self._execute_stake(wallet, pool, amount_wei, amount)
