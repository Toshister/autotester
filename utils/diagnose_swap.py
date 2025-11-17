# utils/diagnose_swap.py
import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config.settings import Config
from services.swap_service import SwapService
from core.wallet_manager import WalletManager
from web3 import Web3


async def diagnose_swap_issues():
    """Диагностика проблем с swap"""
    print("🔧 DIAGNOSING SWAP ISSUES...")

    config = Config()
    wallet_manager = WalletManager(config)
    await wallet_manager.load_wallets()

    if not wallet_manager.wallets:
        print("❌ No wallets loaded")
        return

    wallet = wallet_manager.wallets[0]
    print(f"🔍 Using wallet: {wallet.name} ({wallet.address})")

    # Подключаем к Pharos
    pharos_config = config.get_network_by_name('pharos')
    if not wallet.connect_to_network(pharos_config['rpc_url']):
        print("❌ Failed to connect to Pharos")
        return

    # Создаем swap service
    web3 = Web3(Web3.HTTPProvider(pharos_config['rpc_url']))
    swap_service = SwapService(web3, config)

    # 1. Проверяем балансы токенов
    print("\n💰 TOKEN BALANCES:")
    tokens = config.get_tokens_for_network('pharos')
    for symbol, address in tokens.items():
        if symbol in ['PHRS', 'USDC', 'USDT']:
            balance = await swap_service.get_token_balance(wallet, address)
            balance_formatted = await swap_service._format_amount(balance, address)
            print(f"   {symbol}: {balance_formatted}")

    # 2. Проверяем router контракт
    print("\n🔗 ROUTER CONTRACT:")
    try:
        code = web3.eth.get_code(Web3.to_checksum_address(swap_service.router_address))
        print(f"   ✅ Contract exists: {len(code)} bytes")

        # Пробуем вызвать WETH функцию
        weth = swap_service.router_contract.functions.WETH().call()
        print(f"   ✅ WETH address: {weth}")
    except Exception as e:
        print(f"   ❌ Router contract error: {e}")

    # 3. Проверяем allowance для USDT
    print("\n🔓 ALLOWANCE CHECK:")
    usdt_address = tokens.get('USDT')
    if usdt_address:
        try:
            allowance = await swap_service.check_allowance(wallet, usdt_address, swap_service.router_address)
            print(f"   USDT Allowance: {allowance}")
        except Exception as e:
            print(f"   ❌ Allowance check failed: {e}")

    # 4. Тестируем котировки
    print("\n📊 QUOTE TEST:")
    try:
        usdc_address = tokens.get('USDC')
        usdt_address = tokens.get('USDT')
        if usdc_address and usdt_address:
            # Маленькая сумма для теста
            amount_in = 10 ** 6  # 1 USDC (6 decimals)
            quote = await swap_service.get_swap_quote(amount_in, usdc_address, usdt_address)
            print(f"   USDC -> USDT quote: {quote}")
    except Exception as e:
        print(f"   ❌ Quote failed: {e}")


if __name__ == "__main__":
    asyncio.run(diagnose_swap_issues())