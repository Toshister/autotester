import random
import string
from utils.logger import setup_logger


class DomainService:
    def __init__(self, web3_instance, config):
        self.web3 = web3_instance
        self.config = config
        self.logger = setup_logger("DomainService")

    async def register_random_domain(self, wallet):
        """Регистрация случайного доменного имени"""
        try:
            self.logger.info(f"🌐 Starting domain registration for {wallet.name}")

            # Генерируем случайное доменное имя
            domain_length = random.randint(5, 12)
            domain_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=domain_length))

            # Добавляем случайное расширение
            extensions = ['.test', '.eth', '.crypto', '.blockchain']
            domain_extension = random.choice(extensions)

            full_domain = domain_name + domain_extension

            self.logger.info(f"📝 Simulated domain registration: {wallet.name} registering '{full_domain}'")

            return True

        except Exception as e:
            self.logger.error(f"❌ Domain registration failed for {wallet.name}: {e}")
            return False

    async def register_domain(self, wallet, domain_name: str) -> bool:
        """Регистрация конкретного доменного имени"""
        self.logger.info(f"📝 Simulated domain registration: {wallet.name} -> '{domain_name}'")
        return True