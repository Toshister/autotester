import asyncio
import sys
import os
import signal
import random
from web3 import Web3

sys.path.append(os.path.dirname(__file__))

from config.settings import Config
from core.wallet_manager import WalletManager
from core.transaction_engine import TransactionEngine
from utils.logger import setup_logger
from utils.security import setup_secure_environment
from utils.input_utils import secure_input
from config.constants import is_pharos_network, is_rise_network, is_opn_network, normalize_network_name

setup_secure_environment()


class EVMAutoTester:
    def __init__(self):
        self.config = Config()
        self.wallet_manager = None
        self.transaction_engine = None
        self.logger = setup_logger()
        self.is_running = True

    async def initialize(self, wallet_names=None, target_network=None):
        """Инициализация приложения с выбранными кошельками"""
        self.logger.info("🔄 Initializing EVM Auto Tester...")

        self.wallet_manager = WalletManager(self.config)
        self.transaction_engine = TransactionEngine(self.config, self.wallet_manager)

        # ✅ ПЕРВЫЙ ШАГ: Загружаем кошельки БЕЗ подключения к сетям
        await self.wallet_manager.load_wallets(connect_to_networks=False)

        # Фильтруем кошельки если указаны конкретные
        if wallet_names:
            original_count = len(self.wallet_manager.wallets)
            self.wallet_manager.wallets = [
                wallet for wallet in self.wallet_manager.wallets
                if wallet.name in wallet_names
            ]
            self.logger.debug(f"✅ Selected {len(self.wallet_manager.wallets)} out of {original_count} wallets")

        if not self.wallet_manager.wallets:
            self.logger.error("❌ No wallets available for operation")
            return False

        # ✅ ВТОРОЙ ШАГ: Инициализируем подключения ТОЛЬКО выбранных кошельков
        await self.wallet_manager.initialize_wallet_connections(wallet_names, [target_network] if target_network else None)

        # ✅ ТРЕТИЙ ШАГ: Инициализируем сервисы
        await self.transaction_engine.initialize_services(target_network)

        # ✅ ЧЕТВЕРТЫЙ ШАГ: Устанавливаем веса операций для целевой сети
        if target_network:
            self.transaction_engine.set_network_operation_weights(target_network)
            self.logger.info(f"🎯 Set operation weights for network: {target_network}")

        self.logger.info("✅ EVM Auto Tester initialized successfully")
        return True

    async def shutdown(self):
        """Корректное завершение работы"""
        self.logger.info("🛑 Shutting down EVM Auto Tester...")
        self.is_running = False
        self.logger.info("👋 EVM Auto Tester stopped successfully")

async def select_network_interactive():
    """✅ ИСПРАВЛЕННЫЙ ВЫБОР СЕТИ С ГИБКИМ СООТВЕТСТВИЕМ"""
    config = Config()
    networks = config.get_all_networks()

    if not networks:
        print("❌ Сетей нет. Сначала добавьте сети через меню управления сетями.")
        return None

    print("\n🌐 Выберите сеть:")
    print("=" * 40)

    for i, network in enumerate(networks, 1):
        native_token = network.get('native_token', 'N/A')
        chain_id = network.get('chain_id', 'N/A')
        print(f"{i}. {network['name']} ({native_token}) - ChainID: {chain_id}")

    print(f"{len(networks) + 1}. ↩️ Назад")

    try:
        choice = secure_input(f"\nВыберите сеть (1-{len(networks)}): ").strip()

        if choice == str(len(networks) + 1):
            return None

        if choice.isdigit():
            choice_num = int(choice)
            if 1 <= choice_num <= len(networks):
                selected_network = networks[choice_num - 1]['name']

                # ✅ ДОБАВИМ ОТЛАДОЧНУЮ ИНФОРМАЦИЮ
                normalized = normalize_network_name(selected_network)
                print(f"🔍 DEBUG: Original: '{selected_network}' -> Normalized: '{normalized}'")
                print(f"🔍 DEBUG: Is OPN: {is_opn_network(selected_network)}")
                print(f"🔍 DEBUG: Is Rise: {is_rise_network(selected_network)}")

                print(f"✅ Выбрана сеть: {selected_network}")
                return selected_network

        print("❌ Неверный выбор сети")
        return None

    except Exception as e:
        print(f"❌ Ошибка выбора сети: {e}")
        return None

def get_transaction_count() -> int:
    """Прямой ввод количества транзакций"""
    print("\n🔢 Настройка количества транзакций")
    print("=" * 40)

    while True:
        try:
            count_input = secure_input("Введите количество транзакций для выполнения: ")
            count = int(count_input)

            if count <= 0:
                print("❌ Количество должно быть положительным числом")
                continue
            elif count > 50:
                print("⚠️  Большое количество транзакций. Рекомендуется не более 50.")
                confirm = secure_input("Продолжить? (y/N): ").strip().lower()
                if confirm != 'y':
                    continue

            return count

        except ValueError:
            print("❌ Введите корректное число")

def get_operation_settings():
    """Получение всех настроек для запуска операций"""
    print("\n🎯 Настройка параметров операций")
    print("=" * 50)

    # ✅ ИСПОЛЬЗУЕМ ИСПРАВЛЕННЫЙ ВЫБОР СЕТИ
    network = asyncio.run(select_network_interactive())
    if not network:
        return None, None, None

    # Выбор кошельков
    wallets = WalletManager.select_wallets_interactive()
    if not wallets:
        return None, None, None

    # Количество транзакций
    transaction_count = get_transaction_count()

    return network, wallets, transaction_count

async def run_with_settings(selected_network, selected_wallet_names, transaction_count):
    """Запуск программы с выбранными настройками"""
    app = EVMAutoTester()

    try:
        # ✅ ПЕРЕДАЕМ СЕТЬ ПРИ ИНИЦИАЛИЗАЦИИ
        if await app.initialize(selected_wallet_names, selected_network):
            print(f"\n🚀 Запуск {transaction_count} операций в сети {selected_network}")
            print("=" * 50)

            # ✅ ПРЕДУПРЕЖДЕНИЕ О ДОСТУПНЫХ ОПЕРАЦИЯХ ДЛЯ СЕТИ
            await show_available_operations_for_network(selected_network)

            # Выполняем указанное количество операций в выбранной сети
            await execute_operations_in_network(app, selected_network, transaction_count)

            await app.shutdown()
        else:
            print("❌ Не удалось инициализировать кошельки")

    except KeyboardInterrupt:
        print("\n\n🛑 Программа прервана пользователем")
    except Exception as e:
        print(f"\n\n💥 Ошибка выполнения: {e}")

async def show_available_operations_for_network(network_name: str):
    """✅ ПОКАЗЫВАЕМ ДОСТУПНЫЕ ОПЕРАЦИИ ДЛЯ ВЫБРАННОЙ СЕТИ"""
    normalized_network = normalize_network_name(network_name)

    print(f"\n🔍 Доступные операции для {normalized_network}:")

    if is_pharos_network(normalized_network):
        print("   ✅ Подписки (CashPlus)")
        print("   ❌ Свопы (недоступно)")
        print("   ❌ Трансферы (недоступно)")
    elif is_rise_network(normalized_network):
        print("   ✅ Свопы (Gaspump)")
        print("   ✅ Трансферы")
        print("   ❌ Подписки (недоступно)")
    elif is_opn_network(normalized_network):
        print("   ✅ Трансферы (0.1-0.3% от баланса)")
        print("   ✅ Свопы (OPN → OPNT/WOPN/tUSDT/tBNB)")
        print("   ❌ Подписки (недоступно)")
    else:
        print("   ⚠️  Все операции (режим тестирования)")

async def execute_operations_in_network(app, selected_network, transaction_count):
    """Выполнение операций в конкретной сети с рандомным порядком"""
    # ✅ ИСПОЛЬЗУЕМ НОРМАЛИЗОВАННОЕ ИМЯ СЕТИ
    normalized_network = normalize_network_name(selected_network)

    # ✅ ПЕРЕПОДКЛЮЧАЕМ КОШЕЛЬКИ К ВЫБРАННОЙ СЕТИ ПЕРЕД ДИАГНОСТИКОЙ
    print(f"\n🔌 Подключаем кошельки к сети {normalized_network}...")
    network_config = app.config.get_network_by_name(normalized_network)
    if not network_config:
        print(f"❌ Сеть {normalized_network} не найдена в конфигурации")
        return

    await refresh_wallet_balances_for_network(app.wallet_manager, normalized_network)

    # ✅ ДОБАВЛЯЕМ ИНФОРМАЦИЮ О ДОСТУПНЫХ СЕРВИСАХ
    available_services = list(app.transaction_engine.services.get(normalized_network, {}).keys())
    print(f"🔧 Available services: {available_services}")

    # ПРЕДУПРЕЖДЕНИЕ о реальных транзакциях
    print(f"\n⚠️  ВНИМАНИЕ: Будут выполнены РЕАЛЬНЫЕ транзакции в сети {normalized_network}!")
    print("💸 Будут потрачены реальные средства из ваших кошельков!")

    confirm = secure_input("Продолжить? (y/N): ").strip().lower()
    if confirm != 'y':
        print("❌ Отменено пользователем")
        return

    successful_operations = 0

    # ✅ ПЕРЕМЕШИВАЕМ КОШЕЛЬКИ ПЕРЕД НАЧАЛОМ
    shuffled_wallets = app.wallet_manager.wallets.copy()
    random.shuffle(shuffled_wallets)

    for i in range(transaction_count):
        try:
            # ✅ БЕРЕМ КОШЕЛЬКИ ПО ОЧЕРЕДИ ИЗ ПЕРЕМЕШАННОГО СПИСКА
            wallet_index = i % len(shuffled_wallets)
            wallet = shuffled_wallets[wallet_index]

            print(f"\n🔄 Операция {i + 1}/{transaction_count}: {wallet.name}")

            # ✅ ПЕРЕДАЕМ НОРМАЛИЗОВАННОЕ ИМЯ СЕТИ
            success = await app.transaction_engine.execute_operation_cycle(wallet.name, normalized_network)

            if success:
                successful_operations += 1

            # ✅ СЛУЧАЙНАЯ ПАУЗА МЕЖДУ ОПЕРАЦИЯМИ (15-25 СЕКУНД)
            delay_seconds = random.randint(15, 25)
            print(f"⏳ Ожидание {delay_seconds} секунд перед следующей операцией...")
            await asyncio.sleep(delay_seconds)

        except Exception as e:
            print(f"❌ Операция {i + 1} не удалась: {e}")

    print(f"\n📊 Выполнено операций: {successful_operations}/{transaction_count}")


async def refresh_wallet_balances_for_network(wallet_manager, network_name):
    """Обновление балансов кошельков для конкретной сети"""
    normalized_network = normalize_network_name(network_name)
    network_config = wallet_manager.config.get_network_by_name(normalized_network)

    if not network_config:
        print(f"❌ Сеть {normalized_network} не найдена")
        return

    print(f"\n🔄 Обновление балансов для сети {normalized_network}:")

    for wallet in wallet_manager.wallets:
        try:
            # ✅ ПОДКЛЮЧАЕМ КОШЕЛЕК К СЕТИ
            if wallet.connect_to_network(network_config['rpc_url']):
                # ✅ ПОЛУЧАЕМ АКТУАЛЬНЫЙ БАЛАНС
                balance = wallet.get_balance()
                balance_eth = wallet.web3.from_wei(balance, 'ether')
                native_token = network_config.get('native_token', 'ETH')
                print(f"   ✅ {wallet.name}: {balance_eth:.6f} {native_token}")
            else:
                print(f"   ❌ {wallet.name}: не удалось подключиться")

        except Exception as e:
            print(f"   ❌ {wallet.name}: ошибка - {e}")

async def check_wallet_balances(wallet_names=None, specific_network=None):
    """Проверка баланса кошельков (оптимизированная версия)"""
    config = Config()
    wallet_manager = WalletManager(config)

    # Загружаем кошельки
    await wallet_manager.load_wallets()

    if not wallet_manager.wallets:
        print("❌ No wallets available for balance check")
        return

    # ✅ ИСПОЛЬЗУЕМ НОРМАЛИЗОВАННОЕ ИМЯ СЕТИ
    normalized_network = normalize_network_name(specific_network) if specific_network else None

    # Используем оптимизированный метод без прокси
    await wallet_manager.check_balances_without_proxy(wallet_names, normalized_network)

def check_balance_menu():
    """Меню проверки баланса"""
    config = Config()
    wallet_names = [wallet.get('name') for wallet in config.wallets]

    if not wallet_names:
        print("❌ Кошельков нет для проверки баланса")
        return

    print("\n💰 Проверка баланса")
    print("=" * 30)
    print("1. Проверить все кошельки")
    print("2. Выбрать кошельки")
    print("3. Проверить в конкретной сети")
    print("4. Назад")

    try:
        choice = secure_input("\nВыберите действие (1-4): ").strip()

        if choice == "1":
            asyncio.run(check_wallet_balances())
        elif choice == "2":
            selected_wallets = WalletManager.select_wallets_interactive()
            if selected_wallets:
                asyncio.run(check_wallet_balances(selected_wallets))
        elif choice == "3":
            network_choice = asyncio.run(select_network_interactive())
            if network_choice:
                asyncio.run(check_wallet_balances(specific_network=network_choice))
        elif choice == "4":
            return
        else:
            print("❌ Неверный выбор")
    except Exception as e:
        print(f"❌ Ошибка в меню проверки баланса: {e}")


def wallet_management_menu():
    """Подменю управления кошельками"""
    while True:
        print("\n🎒 Управление кошельками")
        print("=" * 40)
        print("1. ➕ Добавить новый кошелек")
        print("2. 📋 Показать информацию о кошельках")
        print("3. 💰 Проверить баланс кошельков")
        print("4. 🔧 Изменить прокси кошельков")
        print("5. ↩️ Назад")

        choice = secure_input("\nВыберите действие (1-5): ").strip()

        if choice == "1":
            WalletManager.add_wallet_interactive()
        elif choice == "2":
            WalletManager.show_wallet_info()
        elif choice == "3":
            check_balance_menu()
        elif choice == "4":
            WalletManager.edit_wallet_proxy_interactive()
        elif choice == "5":
            break
        else:
            print("❌ Неверный выбор. Попробуйте еще раз.")

def network_management_menu():
    """Меню управления сетями"""
    from core.network_manager import NetworkManager

    network_manager = NetworkManager()

    while True:
        print("\n🌐 Управление сетями и токенами")
        print("=" * 40)
        print("1. 📋 Показать все сети")
        print("2. ➕ Добавить новую сеть")
        print("3. ✏️ Редактировать сеть")
        print("4. 🗑️ Удалить сеть")
        print("5. 🪙 Показать токены сети")
        print("6. ➕ Добавить токены в сеть")
        print("7. ↩️ Назад")

        choice = secure_input("\nВыберите действие (1-7): ").strip()

        if choice == "1":
            network_manager.show_networks_info()
        elif choice == "2":
            network_manager.add_network_interactive()
        elif choice == "3":
            network_manager.edit_network_interactive()
        elif choice == "4":
            network_manager.delete_network_interactive()
        elif choice == "5":
            network_manager.show_tokens_for_network()
        elif choice == "6":
            network_manager.add_tokens_to_network_interactive()
        elif choice == "7":
            break
        else:
            print("❌ Неверный выбор. Попробуйте еще раз.")

def check_environment():
    """Проверка окружения и вывод предупреждений"""
    is_pycharm = 'PYCHARM_HOSTED' in os.environ

    if is_pycharm:
        print("⚠️  Обнаружена среда PyCharm")
        print("💡 Рекомендация: Для максимальной безопасности")
        print("   запускайте программу через системный терминал")
        print("   или убедитесь, что никто не видит ваш экран при вводе приватных ключей!")

def main_menu():
    """Главное меню при запуске"""
    check_environment()

    while True:
        print("\n🚀 EVM Auto Tester - Меню запуска")
        print("=" * 40)
        print("1. 🎒 Управление кошельками")
        print("2. 🌐 Управление сетями и токенами")
        print("3. 🎯 Начать отправку транзакций")
        print("4. 🚪 Выход")

        choice = secure_input("\nВыберите действие (1-4): ").strip()

        if choice == "1":
            wallet_management_menu()

        elif choice == "2":
            network_management_menu()

        elif choice == "3":
            # Получаем все настройки
            network, wallets, count = get_operation_settings()

            if network and wallets and count:
                # ✅ ПОКАЗЫВАЕМ НОРМАЛИЗОВАННОЕ ИМЯ СЕТИ
                normalized_network = normalize_network_name(network)

                print(f"\n✅ Настройки подтверждены:")
                print(f"   🌐 Сеть: {normalized_network}")
                print(f"   🎒 Кошельки: {', '.join(wallets)}")
                print(f"   🔢 Количество операций: {count}")

                # ✅ ПОКАЗЫВАЕМ ПРЕДУПРЕЖДЕНИЕ О ДОСТУПНЫХ ОПЕРАЦИЯХ
                asyncio.run(show_available_operations_for_network(normalized_network))

                confirm = secure_input("\nНачать выполнение? (y/N): ").strip().lower()
                if confirm == 'y':
                    asyncio.run(run_with_settings(normalized_network, wallets, count))
                else:
                    print("❌ Отменено пользователем")

                # Пауза перед возвратом в меню
                input("\n↵ Нажмите Enter чтобы продолжить...")

        elif choice == "4":
            print("👋 До свидания!")
            break
        else:
            print("❌ Неверный выбор. Попробуйте еще раз.")

if __name__ == "__main__":
    print("🌐 EVM Auto Tester - Automated Testnet Operations")
    print("🔒 Secure Multi-Wallet Management with Proxy Support")

    # Показываем меню
    main_menu()
