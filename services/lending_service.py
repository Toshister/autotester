import random
from utils.randomizer import Randomizer
from utils.logger import setup_logger


class LendingService:
    def __init__(self, web3_instance, config):
        self.web3 = web3_instance
        self.config = config
        self.logger = setup_logger("LendingService")

    async def execute_lend(self, wallet):
        """Выполнение операции lending"""
        try:
            self.logger.info(f"🏦 Starting lend operation for {wallet.name}")

            balance = (wallet.web3.eth.get_balance(wallet.address))
            if balance == 0:
                self.logger.warning(f"⚠️ Zero balance for lending in {wallet.name}")
                return False

            # Случайный процент от баланса
            lend_percentage = Randomizer.get_random_percentage(5.0, 15.0)
            lend_amount = int(balance * lend_percentage / 100)

            if lend_amount == 0:
                self.logger.warning("⚠️ Lend amount is zero")
                return False

            self.logger.info(f"💰 Simulated lending: {wallet.name} lending {lend_amount} wei ({lend_percentage:.2f}%)")

            return True

        except Exception as e:
            self.logger.error(f"❌ Lend operation failed for {wallet.name}: {e}")
            return False

    async def execute_borrow(self, wallet):
        """Выполнение операции borrowing"""
        try:
            self.logger.info(f"🏦 Starting borrow operation for {wallet.name}")

            # В тестовом режиме просто логируем
            borrow_amount = random.randint(1000000000000000, 10000000000000000)  # 0.001-0.01 ETH

            self.logger.info(f"📈 Simulated borrowing: {wallet.name} borrowing {borrow_amount} wei")

            return True

        except Exception as e:
            self.logger.error(f"❌ Borrow operation failed for {wallet.name}: {e}")
            return False