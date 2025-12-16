import asyncio
import random
import time
from web3 import Web3

from services.transfer_service import TransferService
from services.swap_service import SwapService
from services.subscription_service import SubscriptionService
from services.staking_service import StakingService
from services.lending_service import LendingService
from core.gas_monitor import GasMonitor
from utils.randomizer import Randomizer
from utils.logger import setup_logger
from config.constants import normalize_network_name, is_pharos_network, is_rise_network, is_opn_network, is_arc_network


class TransactionEngine:
    def __init__(self, config, wallet_manager):
        self.config = config
        self.wallet_manager = wallet_manager
        self.services = {}
        self.logger = setup_logger("TransactionEngine")
        self.gas_monitor = GasMonitor(config)

        # ✅ ИСПРАВЛЕННАЯ ИНИЦИАЛИЗАЦИЯ СТАТИСТИКИ
        self.real_time_stats = {
            'start_time': time.time(),
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'total_gas_used': 0,
            'operations_per_minute': 0,
            'success_rate': 0.0
        }

        # Статистика по кошелькам
        self.wallet_stats = {}

        # ✅ ВЕСА ОПЕРАЦИЙ
        self.operation_weights = {
            'transfer': 0,
            'swap': 0,
            'subscribe_stake': 0,
            'lend_borrow': 0
        }

    def set_network_operation_weights(self, network_name: str):
        """Установка весов операций для конкретной сети"""
        # ✅ ИСПОЛЬЗУЕМ НОРМАЛИЗОВАННОЕ ИМЯ СЕТИ
        normalized_network = normalize_network_name(network_name)

        if is_pharos_network(normalized_network):
            # Для Pharos - подписка/стейк и lend/borrow (внутри 50/50)
            self.operation_weights = {
                'transfer': 0,
                'swap': 0,
                'subscribe_stake': 30,  # 50/50 внутри
                'lend_borrow': 70       # 50/50 внутри
            }
            self.logger.info(f"🎯 Set operation weights for {normalized_network}: Subscribe/Stake + Lend/Borrow")

        elif is_rise_network(normalized_network):
            # Для Rise Testnet - только трансфер (swap отключен)
            self.operation_weights = {
                'transfer': 100,
                'swap': 0,
                'subscribe_stake': 0,
                'lend_borrow': 0
            }
            self.logger.info(f"🎯 Set operation weights for {normalized_network}: Transfers only (swaps disabled)")

        elif is_opn_network(normalized_network):
            self.operation_weights = {
                'transfer': 20,
                'swap': 80,
                'subscribe_stake': 0,
                'lend_borrow': 0
            }
            self.logger.info(f"🎯 Set operation weights for {normalized_network}: Transfer & Swap")

        elif is_arc_network(normalized_network):
            self.operation_weights = {
                'transfer': 20,
                'swap': 80,
                'subscribe_stake': 0,
                'lend_borrow': 0
            }
            self.logger.info(f"🎯 Set operation weights for {normalized_network}: Swap-focused")

        else:
            # Для других сетей - стандартные веса
            self.operation_weights = {
                'transfer': 50,
                'swap': 30,
                'subscribe_stake': 20,
                'lend_borrow': 0
            }
            self.logger.info(f"🎯 Set operation weights for {normalized_network}: Mixed operations")

    async def initialize_services(self, target_network: str = None):
        """Инициализация сервисов (можно ограничить конкретной сетью)"""
        self.logger.info("🔄 Initializing services...")

        networks_to_init = self.config.networks
        if target_network:
            normalized_target = normalize_network_name(target_network)
            filtered = [
                n for n in self.config.networks
                if normalize_network_name(n['name']) == normalized_target
            ]
            if filtered:
                networks_to_init = filtered
            else:
                self.logger.warning(f"⚠️ Target network '{target_network}' not found, initializing all")

        for network in networks_to_init:
            try:
                # Создаем Web3 instance для сети
                web3_instance = Web3(Web3.HTTPProvider(network['rpc_url']))

                # ✅ ТОЛЬКО ОСНОВНЫЕ СЕРВИСЫ (БЕЗ NITRODEX)
                lending_service = LendingService(web3_instance, self.config)
                self.services[network['name']] = {
                    'transfer': TransferService(web3_instance, self.config, self.gas_monitor),
                    'swap': SwapService(web3_instance, self.config, self.gas_monitor),
                    'subscribe': SubscriptionService(web3_instance, self.config, self.gas_monitor),
                    'stake': StakingService(web3_instance, self.config),
                    'lend': lending_service,
                    'borrow': lending_service
                }
                self.logger.info(f"✅ Services initialized for {network['name']}")

            except Exception as e:
                self.logger.error(f"❌ Failed to initialize services for {network['name']}: {e}")

        # Инициализируем статистику для каждого кошелька
        for wallet in self.wallet_manager.wallets:
            self.wallet_stats[wallet.name] = {
                'total_operations': 0,
                'successful_operations': 0,
                'failed_operations': 0,
                'total_gas_used': 0
            }

        self.start_monitoring()

    def start_monitoring(self):
        """Запуск мониторинга в реальном времени"""
        self.real_time_stats['start_time'] = time.time()
        asyncio.create_task(self._real_time_stats_loop())

    async def _real_time_stats_loop(self):
        """Фоновое обновление статистики"""
        while True:
            await asyncio.sleep(30)
            self._recalculate_real_time_stats()

    def _recalculate_real_time_stats(self):
        """Пересчет статистики (можно вызывать вручную)"""
        elapsed_minutes = (time.time() - self.real_time_stats['start_time']) / 60
        if elapsed_minutes > 0:
            self.real_time_stats['operations_per_minute'] = (
                self.real_time_stats['total_operations'] / elapsed_minutes
            )

        # Рассчитываем успешность
        total_ops = self.real_time_stats['total_operations']
        if total_ops > 0:
            successful_ops = self.real_time_stats['successful_operations']
            self.real_time_stats['success_rate'] = (successful_ops / total_ops) * 100
        else:
            self.real_time_stats['success_rate'] = 0.0

        self._display_real_time_stats()

    def _display_real_time_stats(self):
        """Отображение статистики в реальном времени"""
        stats = self.real_time_stats
        self.logger.info(
            f"📊 Real-time Stats: {stats['total_operations']} ops | "
            f"{stats['operations_per_minute']:.1f} op/min | "
            f"Success: {stats['success_rate']:.1f}% | "
            f"✅ {stats['successful_operations']} | ❌ {stats['failed_operations']}"
        )

    async def _execute_swap_operation(self, wallet, network_name: str) -> bool:
        """Выполнение swap операции (только Gaspump)"""
        try:
            service = self.services.get(network_name, {}).get('swap')
            if service:
                return await service.execute_random_swap(wallet, network_name)
            else:
                self.logger.error("❌ Swap service not available")
                return False

        except Exception as e:
            self.logger.error(f"❌ Swap operation failed: {e}")
            return False

    async def _execute_lend_operation(self, wallet, network_name: str) -> bool:
        """Выполнение lend операции для Pharos Atlantic."""
        try:
            service = self.services.get(network_name, {}).get('lend')
            if service:
                return await service.execute_lend(wallet, network_name)
            self.logger.error("❌ Lending service not available")
            return False
        except Exception as e:
            self.logger.error(f"❌ Lending operation failed: {e}")
            return False

    async def _execute_borrow_operation(self, wallet, network_name: str) -> bool:
        """Выполнение borrow операции для Pharos Atlantic."""
        try:
            service = self.services.get(network_name, {}).get('borrow')
            if service:
                return await service.execute_borrow(wallet, network_name)
            self.logger.error("❌ Borrow service not available")
            return False
        except Exception as e:
            self.logger.error(f"❌ Borrow operation failed: {e}")
            return False

    async def execute_operation_cycle(self, wallet_name: str, network_name: str) -> bool:
        """Выполнение одного цикла операций для кошелька"""
        wallet = None
        try:
            # ✅ ИСПОЛЬЗУЕМ СУЩЕСТВУЮЩИЙ МЕТОД get_wallet_by_name
            wallet = self.wallet_manager.get_wallet_by_name(wallet_name)

            if not wallet:
                self.logger.error(f"❌ Wallet {wallet_name} not found")
                return False

            self.logger.info(f"🔁 Starting operation cycle for {wallet_name} on {network_name}")

            # ✅ ОБНОВЛЯЕМ СТАТИСТИКУ ДО выполнения операции
            self.real_time_stats['total_operations'] += 1
            self.wallet_stats[wallet.name]['total_operations'] += 1

            # ✅ ПРОВЕРЯЕМ ЧТО ВЕСА УСТАНОВЛЕНЫ
            if sum(self.operation_weights.values()) == 0:
                self.logger.warning("⚠️ Operation weights not set, using default")
                self.set_network_operation_weights(network_name)

            # Выбираем тип операции на основе весов
            operation_type = Randomizer.weighted_choice(self.operation_weights)

            success = False

            if operation_type == 'transfer':
                self.logger.info(f"🎲 Selected operation: TRANSFER")
                service = self.services.get(network_name, {}).get('transfer')
                if service:
                    success = await service.execute_random_transfer(wallet, network_name)
                else:
                    self.logger.error("❌ Transfer service not available")

            elif operation_type == 'swap':
                self.logger.info(f"🎲 Selected operation: SWAP")
                # ✅ ИСПОЛЬЗУЕМ ТОЛЬКО GASPUMP
                success = await self._execute_swap_operation(wallet, network_name)

            elif operation_type == 'subscribe_stake':
                chosen = random.choice(['subscribe', 'stake'])
                self.logger.info(f"🎲 Selected operation: {chosen.upper()} (from SUBSCRIBE/STAKE 50/50)")
                if chosen == 'subscribe':
                    service = self.services.get(network_name, {}).get('subscribe')
                    if service:
                        success = await service.execute_random_subscription(wallet, network_name)
                    else:
                        self.logger.error("❌ Subscription service not available")
                else:
                    service = self.services.get(network_name, {}).get('stake')
                    if service:
                        success = await service.execute_random_stake(wallet, network_name)
                    else:
                        self.logger.error("❌ Staking service not available")

            elif operation_type == 'lend_borrow':
                chosen = random.choice(['lend', 'borrow'])
                self.logger.info(f"🎲 Selected operation: {chosen.upper()} (from LEND/BORROW 50/50)")
                if chosen == 'lend':
                    success = await self._execute_lend_operation(wallet, network_name)
                else:
                    success = await self._execute_borrow_operation(wallet, network_name)

            # ✅ ОБНОВЛЯЕМ СТАТИСТИКУ ПОСЛЕ выполнения
            if success:
                self.real_time_stats['successful_operations'] += 1
                self.wallet_stats[wallet.name]['successful_operations'] += 1
                self.logger.info(f"✅ Operation completed successfully")
            else:
                self.real_time_stats['failed_operations'] += 1
                self.wallet_stats[wallet.name]['failed_operations'] += 1
                self.logger.warning(f"⚠️ Operation failed")

            return success

        except Exception as e:
            self.logger.error(f"❌ Operation cycle failed: {e}")
            self.real_time_stats['failed_operations'] += 1
            if wallet:
                self.wallet_stats[wallet.name]['failed_operations'] += 1
            return False

    async def run_continuous_operations(self, wallet_names: list, network_name: str,
                                        duration_minutes: int = 60,
                                        operations_per_minute: int = 2):
        """Запуск непрерывных операций с рандомным порядком кошельков"""
        try:
            self.logger.info(f"🚀 Starting continuous operations for {len(wallet_names)} wallets")
            self.logger.info(f"⏰ Duration: {duration_minutes} minutes")
            self.logger.info(f"📊 Target: {operations_per_minute} operations/minute")

            # ✅ УСТАНАВЛИВАЕМ ВЕСА ДЛЯ ВЫБРАННОЙ СЕТИ
            self.set_network_operation_weights(network_name)

            start_time = time.time()
            end_time = start_time + (duration_minutes * 60)
            operation_count = 0

            while time.time() < end_time:
                # ✅ ПЕРЕМЕШИВАЕМ КОШЕЛЬКИ КАЖДЫЙ ЦИКЛ
                shuffled_wallets = random.sample(wallet_names, len(wallet_names))

                for wallet_name in shuffled_wallets:
                    if time.time() >= end_time:
                        break

                    # Выполняем операцию
                    success = await self.execute_operation_cycle(wallet_name, network_name)
                    operation_count += 1

                    # ✅ ОБНОВЛЯЕМ СТАТИСТИКУ В РЕАЛЬНОМ ВРЕМЕНИ
                    self._recalculate_real_time_stats()

                    # ✅ СЛУЧАЙНАЯ ЗАДЕРЖКА ОТ 15 ДО 25 СЕКУНД
                    delay_seconds = random.randint(15, 25)
                    self.logger.info(f"⏳ Waiting {delay_seconds} seconds before next operation...")
                    await asyncio.sleep(delay_seconds)

            # Финальная статистика
            self._print_final_stats(operation_count, start_time)

        except Exception as e:
            self.logger.error(f"❌ Continuous operations failed: {e}")

    def _print_final_stats(self, total_operations: int, start_time: float):
        """Вывод финальной статистики"""
        elapsed_time = time.time() - start_time
        successful_ops = self.real_time_stats['successful_operations']
        failed_ops = self.real_time_stats['failed_operations']

        success_rate = (successful_ops / total_operations * 100) if total_operations > 0 else 0
        ops_per_minute = total_operations / (elapsed_time / 60) if elapsed_time > 0 else 0

        self.logger.info("🎯 FINAL OPERATION STATISTICS")
        self.logger.info(f"⏰ Total time: {elapsed_time / 60:.2f} minutes")
        self.logger.info(f"📊 Total operations: {total_operations}")
        self.logger.info(f"✅ Successful: {successful_ops}")
        self.logger.info(f"❌ Failed: {failed_ops}")
        self.logger.info(f"📈 Success rate: {success_rate:.1f}%")
        self.logger.info(f"🚀 Operations per minute: {ops_per_minute:.1f}")

        # Статистика по кошелькам
        self._log_wallet_stats()

    def _log_wallet_stats(self):
        """Логирование статистики по кошелькам"""
        self.logger.info("📈 Wallet Statistics:")
        for wallet_name, stats in self.wallet_stats.items():
            success_rate = (stats['successful_operations'] / stats['total_operations'] * 100) if stats['total_operations'] > 0 else 0

            self.logger.info(
                f"   {wallet_name}: {stats['successful_operations']}/{stats['total_operations']} "
                f"({success_rate:.1f}%)"
            )

    def get_wallet_statistics(self) -> dict:
        """Получить статистику по кошелькам"""
        return self.wallet_stats.copy()

    def get_current_stats(self) -> dict:
        """Получение текущей статистики"""
        return self.real_time_stats.copy()

    async def execute_random_operation(self, wallet, network_name: str) -> bool:
        """Legacy метод для совместимости"""
        return await self.execute_operation_cycle(wallet.name, network_name)

    async def run_single_operation(self, wallet_name: str, network_name: str, operation_type: str) -> bool:
        """Выполнение одной конкретной операции"""
        try:
            wallet = self.wallet_manager.get_wallet_by_name(wallet_name)
            if not wallet:
                self.logger.error(f"❌ Wallet {wallet_name} not found")
                return False

            self.logger.info(f"🎯 Executing single {operation_type} operation for {wallet_name}")

            success = False

            if operation_type == 'transfer':
                service = self.services.get(network_name, {}).get('transfer')
                if service:
                    success = await service.execute_random_transfer(wallet, network_name)
                else:
                    self.logger.error("❌ Transfer service not available")

            elif operation_type == 'swap':
                # ✅ ТОЛЬКО GASPUMP
                success = await self._execute_swap_operation(wallet, network_name)

            elif operation_type == 'subscribe_stake':
                # 50/50 между подпиской и стейком
                chosen = random.choice(['subscribe', 'stake'])
                if chosen == 'subscribe':
                    service = self.services.get(network_name, {}).get('subscribe')
                    if service:
                        success = await service.execute_random_subscription(wallet, network_name)
                    else:
                        self.logger.error("❌ Subscription service not available")
                else:
                    service = self.services.get(network_name, {}).get('stake')
                    if service:
                        success = await service.execute_random_stake(wallet, network_name)
                    else:
                        self.logger.error("❌ Staking service not available")

            elif operation_type == 'lend_borrow':
                # 50/50 между lend и borrow
                chosen = random.choice(['lend', 'borrow'])
                if chosen == 'lend':
                    success = await self._execute_lend_operation(wallet, network_name)
                else:
                    success = await self._execute_borrow_operation(wallet, network_name)

            else:
                self.logger.error(f"❌ Unknown operation type: {operation_type}")
                return False

            # ✅ ОБНОВЛЯЕМ СТАТИСТИКУ
            self.real_time_stats['total_operations'] += 1
            self.wallet_stats[wallet.name]['total_operations'] += 1

            if success:
                self.real_time_stats['successful_operations'] += 1
                self.wallet_stats[wallet.name]['successful_operations'] += 1
            else:
                self.real_time_stats['failed_operations'] += 1
                self.wallet_stats[wallet.name]['failed_operations'] += 1

            return success

        except Exception as e:
            self.logger.error(f"❌ Single operation failed: {e}")
            self.real_time_stats['failed_operations'] += 1
            if wallet:
                self.wallet_stats[wallet.name]['failed_operations'] += 1
            return False
