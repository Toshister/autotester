import random
from types import SimpleNamespace

import pytest
from web3 import Web3

from services.swap_service import SwapService


class DummyConfig:
    def __init__(self):
        self.tokens_arc = {
            "USDC": "0x3600000000000000000000000000000000000000",
            "WUSDC": "0x911b4000D3422F482F4062a913885f7b035382Df",
            "TST": "0xb2B6dA55472A9077B45Bd9CC57C42E107c56f18e",
            "SYN": "0xc5124c846c6e6307986988dfb7e743327aa05f19",
            "USDT": "0x175cdb1d338945f0d851a741ccf787d343e57952",
        }
        self.tokens_opn = {
            "OPN": "0x0000000000000000000000000000000000000000",
            "OPNT": "0x2aEc1Db9197Ff284011A6A1d0752AD03F5782B0d",
            "WOPN": "0xBc022C9dEb5AF250A526321d16Ef52E39b4DBD84",
            "tUSDT": "0x3e01b4d892E0D0A219eF8BBe7e260a6bc8d9B31b",
            "tBNB": "0x92cF36713a5622351c9489D5556B90B321873607",
        }

    def get_tokens_for_network(self, network_name: str):
        if "opn" in network_name.lower():
            return self.tokens_opn
        return self.tokens_arc

    def get_network_by_name(self, network_name: str):
        if "opn" in network_name.lower():
            return {"name": network_name, "native_token": "OPN"}
        return {"name": network_name, "native_token": "USDC"}

    def get_network_by_chain_id(self, chain_id: int):
        mapping = {
            984: {"name": "OPN Testnet"},
            5042002: {"name": "Arc Testnet"},
        }
        return mapping.get(chain_id, {"name": "Unknown"})


class FakeEth:
    def __init__(self, chain_id: int):
        self.chain_id = chain_id
        self.gas_price = Web3.to_wei(7, "gwei")

    def get_block(self, *_args, **_kwargs):
        return {"timestamp": 123}

    def get_transaction_count(self, *_args, **_kwargs):
        return 0

    def get_balance(self, *_args, **_kwargs):
        return Web3.to_wei(1, "ether")

    def send_raw_transaction(self, *_args, **_kwargs):
        return b"\x01"

    def wait_for_transaction_receipt(self, *_args, **_kwargs):
        return SimpleNamespace(status=1, hex=lambda: "0x01")

    def contract(self, *_args, **_kwargs):
        return SimpleNamespace(functions=SimpleNamespace())


class FakeWeb3:
    def __init__(self, chain_id: int):
        self.eth = FakeEth(chain_id)
        self.codec = SimpleNamespace(encode=lambda _types, _values: b"")

    @staticmethod
    def to_wei(value, unit):
        return Web3.to_wei(value, unit)

    @staticmethod
    def from_wei(value, unit):
        return Web3.from_wei(value, unit)

    def is_connected(self):
        return True


@pytest.mark.asyncio
async def test_opn_native_to_token_respects_gas_reserve(monkeypatch):
    """Native OPN swap keeps 0.02 reserve and forwards spendable amount."""
    monkeypatch.setattr(SwapService, "_initialize_router", lambda self: None)
    swap_service = SwapService(FakeWeb3(chain_id=984), DummyConfig())

    captured = {}
    monkeypatch.setattr(
        swap_service,
        "_snapshot_token_balances",
        lambda _wallet, _tokens: {"__native__": Web3.to_wei(0.05, "ether")},
    )
    monkeypatch.setattr(
        swap_service,
        "_perform_opn_swap",
        lambda _wallet, amount, _wopn, _target, target_symbol: captured.update(
            {"amount": amount, "target": target_symbol}
        )
        or True,
    )

    choice_iter = iter([3, "OPNT"])  # precision digits, then target symbol
    monkeypatch.setattr(random, "random", lambda: 0.1)
    monkeypatch.setattr(random, "uniform", lambda _a, _b: 5.0)
    monkeypatch.setattr(random, "choice", lambda seq: next(choice_iter))

    wallet = SimpleNamespace(address="0x" + "1" * 40, web3=swap_service.web3)
    result = await swap_service._execute_opn_swap(wallet, "opn testnet")

    expected_amount = 2_000_000_000_000_000  # 0.002 OPN in wei-equivalent
    assert result is True
    assert captured["amount"] == expected_amount
    assert captured["target"] == "OPNT"


@pytest.mark.asyncio
async def test_arc_defi_skips_when_usdc_below_threshold(monkeypatch):
    """DeFi router should be skipped if USDC balance < 80."""
    monkeypatch.setattr(SwapService, "_initialize_router", lambda self: None)
    swap_service = SwapService(FakeWeb3(chain_id=5042002), DummyConfig())
    swap_service.arc_defi_router_contract = SimpleNamespace(
        address="0x" + "2" * 40, functions=SimpleNamespace()
    )
    monkeypatch.setattr(swap_service, "get_token_decimals", lambda _addr: 6)

    tokens = swap_service.config.get_tokens_for_network("arc testnet")
    nonzero_tokens = {"USDC": int(1 * 10**6)}  # 1 USDC with 6 decimals
    wallet = SimpleNamespace(address="0x" + "3" * 40)

    result = await swap_service._execute_arc_defi_swap(wallet, tokens, nonzero_tokens)

    assert result is False
