from utils.randomizer import Randomizer
from utils.logger import setup_logger


class StakingService:
    def __init__(self, web3_instance, config):
        self.web3 = web3_instance
        self.config = config
        self.logger = config.logger

    async def execute_stake(self, wallet):
        """Выполнение операции staking"""
        try:
            self.logger.info(f"🎯 Starting stake operation for {wallet.name}")

            # ПРОВЕРЯЕМ что кошелек подключен к сети
            if not wallet.web3:
                self.logger.error(f"❌ Wallet {wallet.name} not connected to any network")
                return False

            balance = wallet.web3.eth.get_balance(wallet.address)  # Используем wallet.web3
            if balance == 0:
                self.logger.warning(f"⚠️ Zero balance for staking in {wallet.name}")
                return False

            # Случайный процент от баланса
            stake_percentage = Randomizer.get_random_percentage(10.0, 30.0)
            stake_amount = int(balance * stake_percentage / 100)

            if stake_amount == 0:
                self.logger.warning("⚠️ Stake amount is zero")
                return False

            self.logger.info(f"🔒 Simulated staking: {wallet.name} staking {stake_amount} wei ({stake_percentage:.2f}%)")

            return True

        except Exception as e:
            self.logger.error(f"❌ Stake operation failed for {wallet.name}: {e}")
            return False

    async def execute_unstake(self, wallet):
        """Выполнение операции unstaking"""
        try:
            self.logger.info(f"🎯 Starting unstake operation for {wallet.name}")

            # В тестовом режиме просто логируем
            unstake_amount = random.randint(1000000000000000, 5000000000000000)

            self.logger.info(f"🔓 Simulated unstaking: {wallet.name} unstaking {unstake_amount} wei")

            return True

        except Exception as e:
            self.logger.error(f"❌ Unstake operation failed for {wallet.name}: {e}")
            return False