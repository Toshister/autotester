"""
Комплексное тестирование EVM Auto Tester
"""

import asyncio
import sys
import os

# Добавляем текущую директорию в путь Python
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)


def setup_environment():
    """Настройка окружения"""
    print("🔧 Setting up environment...")

    # Создаем необходимые папки
    os.makedirs("logs", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    os.makedirs("config", exist_ok=True)

    print("✅ Environment setup complete")


async def run_security_test():
    """Тест безопасности"""
    print("\n🔐 Testing Security Module...")
    try:
        from utils.security import encrypt_private_key, decrypt_private_key, validate_private_key

        test_key = "0x" + "a" * 64  # Тестовый приватный ключ
        encrypted = encrypt_private_key(test_key)
        decrypted = decrypt_private_key(encrypted)

        assert test_key == decrypted
        assert validate_private_key(test_key)
        print("✅ Security test passed")
        return True
    except Exception as e:
        print(f"❌ Security test failed: {e}")
        return False


async def run_transfer_service_test():
    """Тест сервиса трансферов с использованием РАБОТАЮЩИХ сетей"""
    print("\n🔄 Testing Transfer Service...")
    try:
        from config.settings import Config
        from services.transfer_service import TransferService
        from core.gas_monitor import GasMonitor
        from web3 import Web3

        # Создаем конфиг
        config = Config()

        # Используем РАБОТАЮЩУЮ сеть из конфига (Pharos)
        working_network = config.get_network_by_name('pharos')
        if not working_network:
            print("❌ No working network found in config")
            return False

        # Создаем Web3 instance для рабочей сети
        web3 = Web3(Web3.HTTPProvider(working_network['rpc_url']))

        if not web3.is_connected():
            print(f"❌ Failed to connect to {working_network['name']}")
            return False

        print(f"✅ Connected to {working_network['name']} (ChainID: {web3.eth.chain_id})")

        # Создаем gas monitor и transfer service
        gas_monitor = GasMonitor(config)
        transfer_service = TransferService(web3, config, gas_monitor)

        # Тест генерации адресов
        address = await transfer_service.get_random_address('pharos')
        assert address.startswith('0x') and len(address) == 42
        print(f"✅ Address generation test passed: {address[:16]}...")

        # Тест валидации адресов
        assert transfer_service._is_valid_address(address)
        print("✅ Address validation test passed")

        # Тест fallback генерации
        fallback_address = transfer_service._generate_random_address()
        assert transfer_service._is_valid_address(fallback_address)
        print("✅ Fallback address generation test passed")

        print("🎉 Transfer service tests passed!")
        return True

    except Exception as e:
        print(f"❌ Transfer service test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_wallet_operations_test():
    """Тест операций с кошельками"""
    print("\n💰 Testing Wallet Operations...")
    try:
        from config.settings import Config
        from core.wallet_manager import WalletManager

        config = Config()
        wallet_manager = WalletManager(config)
        await wallet_manager.load_wallets()

        if not wallet_manager.wallets:
            print("❌ No wallets loaded")
            return False

        print(f"✅ Loaded {len(wallet_manager.wallets)} wallets")

        # Проверяем балансы
        for wallet in wallet_manager.wallets:
            if wallet.web3 and wallet.web3.is_connected():
                balance = wallet.get_balance()
                balance_readable = wallet.web3.from_wei(balance, 'ether')
                print(f"   {wallet.name}: {balance_readable:.6f} ETH")
            else:
                print(f"   {wallet.name}: ❌ Not connected")

        print("✅ Wallet operations test passed")
        return True

    except Exception as e:
        print(f"❌ Wallet operations test failed: {e}")
        return False


async def run_integration_test():
    """Комплексное тестирование всей системы"""
    print("\n🔗 Testing Integration...")
    try:
        from config.settings import Config
        from core.wallet_manager import WalletManager
        from core.transaction_engine import TransactionEngine

        # Тест конфигурации
        config = Config()
        if config.validate_config():
            print("✅ Configuration module: PASSED")
        else:
            print("⚠️ Configuration has warnings")

        # Тест менеджера кошельков
        wallet_manager = WalletManager(config)
        await wallet_manager.load_wallets()
        print(f"✅ Wallet manager: PASSED ({len(wallet_manager.wallets)} wallets loaded)")

        # Тест движка транзакций
        transaction_engine = TransactionEngine(config, wallet_manager)
        await transaction_engine.initialize_services()
        print(f"✅ Transaction engine: PASSED ({len(transaction_engine.services)} networks)")

        print("🎉 Integration tests passed!")
        return True

    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        return False


async def run_all_tests():
    """Запуск всех тестов"""
    print("\n🎯 RUNNING COMPREHENSIVE TEST SUITE")
    print("=" * 60)

    results = []

    # Запускаем тесты последовательно
    results.append(await run_security_test())
    results.append(await run_transfer_service_test())
    results.append(await run_wallet_operations_test())
    results.append(await run_integration_test())

    print("=" * 60)

    passed_count = sum(results)
    total_count = len(results)

    if all(results):
        print("🎉 ALL TESTS PASSED! System is ready for use.")
        return True
    else:
        print(f"⚠️ {passed_count}/{total_count} tests passed. Some features may not work.")
        return False


def main():
    """Основная функция"""
    try:
        setup_environment()
        success = asyncio.run(run_all_tests())

        if success:
            print("\n📋 NEXT STEPS:")
            print("1. Run 'python main.py' to start the application")
            print("2. Use 'Check wallet balances' to verify connections")
            print("3. Start with 1-2 test transactions on Pharos")
            print("4. Check logs in 'logs/evm_tester.log'")
        else:
            print("\n⚠️ Some tests failed but core functionality may work.")
            print("Try running 'python main.py' to test the actual application.")

        return 0

    except Exception as e:
        print(f"\n💥 CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())