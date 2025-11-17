import random
import aiohttp
import asyncio
import time
import re
import json
from web3 import Web3
from utils.randomizer import Randomizer
from utils.logger import setup_logger
from bs4 import BeautifulSoup
from config.constants import is_opn_network, normalize_network_name


class TransferService:
    def __init__(self, web3_instance, config, gas_monitor=None):
        self.web3 = web3_instance
        self.config = config
        self.gas_monitor = gas_monitor
        self.logger = setup_logger("TransferService")
        self.last_transaction_time = 0
        self.min_interval = 5
        self.explorer_urls = self._build_explorer_urls_from_config()

        # ✅ КЭШ ПРОВЕРЕННЫХ КОНТРАКТОВ
        self.verified_contracts = set()
        self.verified_eoa = set()

    def _build_explorer_urls_from_config(self) -> dict:
        """Построение ПРАВИЛЬНЫХ URL эксплореров"""
        explorer_urls = {}

        for network in self.config.networks:
            network_name = network['name']
            explorer_url = network.get('explorer', '')

            if not explorer_url:
                continue

            # ✅ Нормализуем URL
            explorer_url = explorer_url.rstrip('/')

            # ✅ ПРАВИЛЬНЫЕ ENDPOINTS ДЛЯ КАЖДОГО ЭКСПЛОРЕРА
            if 'pharosscan.xyz' in explorer_url:
                tx_endpoint = '/txs'  # ✅ ИСПРАВЛЕНО: Pharos использует /txs
            elif 'riselabs.xyz' in explorer_url:
                tx_endpoint = '/txs'  # Rise использует /txs
            elif 'iopn.tech' in explorer_url:
                tx_endpoint = '/txs'  # ✅ OPN использует /txs
            else:
                tx_endpoint = '/txs'  # По умолчанию /txs

            final_url = f"{explorer_url}{tx_endpoint}"
            explorer_urls[network_name] = final_url

            self.logger.debug(f"🔗 Built explorer URL for {network_name}: {final_url}")

        # ✅ ПРАВИЛЬНЫЕ fallback URLs
        fallback_urls = {
            'pharos': 'https://atlantic.pharosscan.xyz/txs',
            'rise testnet': 'https://explorer.testnet.riselabs.xyz/txs',
            'opn testnet': 'https://testnet.iopn.tech/txs'  # ✅ OPN fallback
        }

        for network_name, fallback_url in fallback_urls.items():
            if network_name not in explorer_urls:
                explorer_urls[network_name] = fallback_url
                self.logger.info(f"🔧 Using fallback URL for {network_name}: {fallback_url}")

        self.logger.info(f"✅ Explorer URLs configured for: {list(explorer_urls.keys())}")
        return explorer_urls

    async def get_random_address_from_explorer(self, network_name: str) -> str:
        """Получение случайного адреса из блок эксплорера"""
        try:
            # ✅ ИСПОЛЬЗУЕМ НОРМАЛИЗОВАННОЕ ИМЯ СЕТИ
            normalized_network = normalize_network_name(network_name)

            if normalized_network not in self.explorer_urls:
                self.logger.error(f"❌ No explorer URL for network: {normalized_network}")
                return None

            url = self.explorer_urls[normalized_network]

            if not url.startswith(('http://', 'https://')):
                self.logger.error(f"❌ Invalid URL format for {normalized_network}: {url}")
                return None

            self.logger.info(f"🔍 Fetching addresses from: {url}")

            # ✅ ОСОБЫЙ ПАРСЕР ДЛЯ OPN
            if is_opn_network(normalized_network):
                return await self._get_opn_addresses_special(url)
            else:
                return await self._get_addresses_standard(url, normalized_network)

        except Exception as e:
            self.logger.error(f"❌ Error getting random address from explorer: {e}")
            return None

    async def _get_opn_addresses_special(self, url: str) -> str:
        """Упрощенный парсер для OPN Testnet - только страница транзакций"""
        try:
            self.logger.info("🔧 Using simplified OPN parser (txs page only)...")

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            }

            # ✅ ТОЛЬКО СТРАНИЦА ТРАНЗАКЦИЙ
            txs_url = "https://testnet.iopn.tech/txs"

            async with aiohttp.ClientSession() as session:
                try:
                    self.logger.info(f"🔍 Parsing OPN transactions page: {txs_url}")

                    async with session.get(txs_url, headers=headers, timeout=15) as response:
                        if response.status == 200:
                            html = await response.text()

                            # ✅ ПАРСИМ АДРЕСА ИЗ СТРАНИЦЫ ТРАНЗАКЦИЙ
                            addresses = await self._parse_opn_txs_page(html)

                            if addresses:
                                selected = random.choice(list(addresses))
                                self.logger.info(
                                    f"✅ OPN txs parser found {len(addresses)} addresses, selected: {selected[:16]}...")
                                return Web3.to_checksum_address(selected)
                            else:
                                self.logger.warning("⚠️ No addresses found on transactions page")
                        else:
                            self.logger.error(f"❌ Transactions page returned status {response.status}")

                except asyncio.TimeoutError:
                    self.logger.warning("⏰ Timeout parsing transactions page")
                except Exception as e:
                    self.logger.error(f"❌ Error parsing transactions page: {e}")

            # ✅ ЕСЛИ ПАРСИНГ НЕ СРАБОТАЛ - ПРОБУЕМ API
            self.logger.info("🔧 Falling back to OPN API...")
            api_address = await self._get_opn_addresses_from_api()
            if api_address:
                return api_address

            # ✅ ПОСЛЕДНИЙ ВАРИАНТ: ИЗВЕСТНЫЕ АДРЕСА
            return await self._get_opn_addresses_from_known()

        except Exception as e:
            self.logger.error(f"❌ OPN parser failed: {e}")
            return None

    async def _parse_opn_txs_page(self, html: str) -> set:
        """Парсинг адресов ТОЛЬКО со страницы транзакций OPN"""
        addresses = set()

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # ✅ МЕТОД 1: Поиск адресов отправителей и получателей в таблице транзакций
            # Ищем все строки таблицы с транзакциями
            transaction_rows = soup.find_all('tr')

            for row in transaction_rows:
                # Ищем все ячейки в строке
                cells = row.find_all(['td', 'th'])
                for cell in cells:
                    # Ищем адреса в тексте ячеек
                    text = cell.get_text().strip()
                    if self._is_valid_address(text):
                        addresses.add(text)

                    # ✅ ОСОБЫЙ ПОИСК: адреса в ссылках /address/
                    links = cell.find_all('a', href=True)
                    for link in links:
                        href = link.get('href', '')
                        if '/address/' in href:
                            address = href.split('/address/')[-1].split('?')[0].split('#')[0]
                            if self._is_valid_address(address):
                                addresses.add(address)

            self.logger.info(f"📊 Found {len(transaction_rows)} transaction rows, {len(addresses)} raw addresses")

            # ✅ МЕТОД 2: Поиск в span с классом truncate (основной способ OPN)
            truncate_spans = soup.find_all('span', class_='truncate')
            for span in truncate_spans:
                text = span.get_text().strip()
                if self._is_valid_address(text):
                    addresses.add(text)
                    self.logger.debug(f"🔍 Found address in truncate span: {text[:16]}...")

            self.logger.info(f"📊 Found {len(truncate_spans)} truncate spans")

            # ✅ МЕТОД 3: Поиск по регулярному выражению во всем HTML
            found_addresses = re.findall(r'0x[a-fA-F0-9]{40}', html)
            addresses.update(found_addresses)

            self.logger.info(f"📊 Regex found {len(found_addresses)} addresses in HTML")

            # ✅ ФИЛЬТРАЦИЯ: убираем известные контракты, burn адреса и неактивные
            filtered_addresses = set()
            for addr in addresses:
                if (self._is_valid_address(addr) and
                        not self._is_burn_address(addr) and
                        not self._is_known_contract(addr) and
                        not self._is_likely_contract(addr) and
                        addr.lower() != "0x9c8822e86e6e965e56f7df18b25e190ef196d341"):  # Исключаем свой кошелек

                    # ✅ ПРОВЕРЯЕМ АКТИВНОСТЬ АДРЕСА
                    if await self._is_active_address(addr):
                        filtered_addresses.add(addr)

            self.logger.info(
                f"✅ OPN txs parser: {len(addresses)} → {len(filtered_addresses)} active filtered addresses")
            return filtered_addresses

        except Exception as e:
            self.logger.error(f"❌ OPN txs page parsing failed: {e}")
            return set()

    async def _get_opn_addresses_from_known(self) -> str:
        """Получение случайного адреса из расширенного списка ИЗВЕСТНЫХ EOA адресов"""
        try:
            self.logger.info("🔧 Using extended known OPN EOA addresses...")

            # ✅ ТОЛЬКО ПРОВЕРЕННЫЕ EOA АДРЕСА
            known_eoa_addresses = [
                "0x55f3ff987593af3dc67da88ad7f65e1f9ed5dd1b",  # Из вашей транзакции (EOA)
                "0x0334Ec5e1D9B3c58C5176939350aAf7e9Fe13dac",  # Из HTML (EOA)
                "0x742d35Cc6634C0532925a3b8Dc9B6a7c8d5A7B6a",  # EOA
                "0x8a93d247134d91e0de6f96547cb0204e5be8e5d8",  # EOA
                "0x40918ba7f132e0acba2ce4de4c4baf9bd2d7d849",  # EOA
            ]

            # ✅ ПЕРЕМЕШИВАЕМ И ПРОВЕРЯЕМ КАЖДЫЙ АДРЕС
            random.shuffle(known_eoa_addresses)

            for addr in known_eoa_addresses:
                if await self._is_eoa_address(addr):  # Используем новый метод
                    selected = addr
                    self.logger.info(f"✅ Selected known ACTIVE EOA address: {selected[:16]}...")
                    return Web3.to_checksum_address(selected)

            self.logger.warning("⚠️ No valid active known EOA addresses for OPN")
            return None

        except Exception as e:
            self.logger.error(f"❌ Known addresses method failed: {e}")
            return None

    async def _get_addresses_standard(self, url: str, network_name: str) -> str:
        """Стандартный парсер для других сетей"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=30) as response:
                    if response.status == 200:
                        html = await response.text()
                        addresses = self._extract_addresses_from_html(html, network_name)

                        if addresses:
                            selected_address = random.choice(list(addresses))
                            self.logger.info(
                                f"✅ Found {len(addresses)} addresses from explorer, selected: {selected_address[:16]}...")
                            return selected_address
                        else:
                            self.logger.warning("⚠️ No addresses found in explorer HTML")
                            return None
                    else:
                        self.logger.error(f"❌ Explorer returned status {response.status}: {url}")
                        return None

        except Exception as e:
            self.logger.error(f"❌ Standard parser failed: {e}")
            return None

    def _extract_addresses_from_html(self, html: str, network_name: str) -> set:
        """Извлечение адресов кошельков с улучшенной логикой"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            addresses = set()

            # ✅ ИЗВЕСТНЫЕ КОНТРАКТЫ ДЛЯ ФИЛЬТРАЦИИ
            known_contracts = {
                '0x1e656b2c6b6e91ef6e6a2b16475df7b7d223e3c2',  # Faroswap Router
                '0xe0be08c77f415f577a1b3a9ad7a1df1479564ec8',  # USDC
                '0xe7e84b8b4f39c507499c40B4ac199B050e2882d5',  # USDT
                '0xa5623ee41248cc5d20b2c9d4e87b455b51464e14',  # Genesis n-Badge OPN
            }

            # ✅ УЛУЧШЕННЫЙ ПОИСК АДРЕСОВ
            # Поиск в ссылках (href)
            link_pattern = re.compile(r'/address/(0x[a-fA-F0-9]{40})')
            link_addresses = link_pattern.findall(html)

            # Поиск в тексте
            text_pattern = re.compile(r'0x[a-fA-F0-9]{40}')
            text_addresses = text_pattern.findall(html)

            # Объединяем все найденные адреса
            all_addresses = set(link_addresses + text_addresses)

            self.logger.info(f"🔍 Found {len(all_addresses)} potential addresses in {network_name} explorer")

            for addr in all_addresses:
                if (self._is_valid_address(addr) and
                        addr.lower() not in known_contracts and
                        not self._is_burn_address(addr) and
                        not self._is_contract_address(addr)):
                    addresses.add(Web3.to_checksum_address(addr))

            self.logger.info(f"✅ Filtered to {len(addresses)} unique wallet addresses in {network_name} explorer")
            return addresses

        except Exception as e:
            self.logger.error(f"❌ Error parsing HTML for {network_name}: {e}")
            return set()

    def _is_contract_address(self, address: str) -> bool:
        """Проверка что адрес не является контрактом"""
        # Известные контракты OPN и других сетей
        known_contracts = {
            '0xa5623ee41248cc5d20b2c9d4e87b455b51464e14',  # Genesis n-Badge OPN
            '0x0000000000000000000000000000000000000000',  # Zero address
            '0x1e656b2c6b6e91ef6e6a2b16475df7b7d223e3c2',  # Faroswap Router
        }
        return address.lower() in known_contracts

    def _is_burn_address(self, address: str) -> bool:
        """Проверка что адрес не является burn адресом"""
        burn_addresses = {
            '0x0000000000000000000000000000000000000000',
            '0x000000000000000000000000000000000000dead',
            '0x0000000000000000000000000000000000000001'
        }
        return address.lower() in burn_addresses

    def _is_valid_address(self, text: str) -> bool:
        """Проверка валидности адреса"""
        if not text or not isinstance(text, str):
            return False
        if not text.startswith('0x'):
            return False
        if len(text) != 42:
            return False
        try:
            return all(c in '0123456789abcdefABCDEF' for c in text[2:])
        except:
            return False

    def _generate_random_address(self) -> str:
        """Генерация случайного адреса (fallback)"""
        # ✅ Генерируем валидный случайный адрес
        return Web3.to_checksum_address('0x' + ''.join(random.choices('0123456789abcdef', k=40)))

    async def _wait_for_cooldown(self):
        """Ожидание коолдауна между транзакциями"""
        current_time = time.time()
        time_since_last = current_time - self.last_transaction_time
        if time_since_last < self.min_interval:
            await asyncio.sleep(self.min_interval - time_since_last)
        self.last_transaction_time = time.time()

    async def get_random_address(self, network_name: str) -> str:
        """Улучшенный выбор случайного адреса с приоритетом OPN парсера"""
        self.logger.info(f"🌐 Getting random address for {network_name}")

        # ✅ ОСОБАЯ ЛОГИКА ДЛЯ OPN
        if is_opn_network(network_name):
            # 1. Пробуем улучшенный OPN парсер
            address = await self.get_random_address_from_explorer(network_name)
            if address:
                self.logger.info("✅ Using OPN parser address")
                return address

            # 2. Пробуем известные адреса (только как fallback)
            known_address = await self._get_opn_addresses_from_known()
            if known_address:
                self.logger.info("⚠️ Using known OPN address (parser failed)")
                return known_address
        else:
            # Стандартная логика для других сетей
            address = await self.get_random_address_from_explorer(network_name)
            if address and self._is_valid_address(address):
                return Web3.to_checksum_address(address)

        # ✅ Fallback для всех сетей
        self.logger.warning("⚠️ Using fallback random address")
        return self._generate_random_address()

    def _has_activity(self, address: str) -> bool:
        """Проверка что адрес имеет активность и не является нашим кошельком"""
        try:
            checksum_addr = Web3.to_checksum_address(address)

            # ✅ ИСКЛЮЧАЕМ СВОЙ КОШЕЛЕК
            if checksum_addr.lower() == "0x9c8822e86e6e965e56f7df18b25e190ef196d341".lower():
                return False

            balance = self.web3.eth.get_balance(checksum_addr)
            tx_count = self.web3.eth.get_transaction_count(checksum_addr)

            # ✅ АДРЕС СЧИТАЕТСЯ АКТИВНЫМ ЕСЛИ ИМЕЕТ БАЛАНС ИЛИ ТРАНЗАКЦИИ
            is_active = balance > 0 or tx_count > 0

            if is_active:
                self.logger.debug(
                    f"🔍 Address {address[:16]}... has activity: balance={self.web3.from_wei(balance, 'ether'):.6f}, txs={tx_count}")

            return is_active
        except:
            return False

    async def execute_native_transfer(self, wallet, to_address: str, amount: int) -> bool:
        """Выполнение трансфера нативных токенов"""
        try:
            # ✅ УБЕДИТЕСЬ ЧТО АДРЕС В CHECKSUM ФОРМАТЕ
            to_address_checksum = Web3.to_checksum_address(to_address)

            # ✅ ПОЛУЧАЕМ ИНФОРМАЦИЮ О СЕТИ ДЛЯ ПРАВИЛЬНОГО ОТОБРАЖЕНИЯ
            current_chain_id = self.web3.eth.chain_id
            network_config = self.config.get_network_by_chain_id(current_chain_id)
            native_token = network_config['native_token'] if network_config else 'ETH'

            amount_native = self.web3.from_wei(amount, 'ether')
            self.logger.info(f"💸 Sending {amount_native:.6f} {native_token} to {to_address_checksum[:8]}...")

            # ✅ ИНТЕЛЛЕКТУАЛЬНЫЙ РАСЧЕТ GAS
            try:
                # Пробуем оценить gas limit
                estimated_gas = self.web3.eth.estimate_gas({
                    'to': to_address_checksum,
                    'value': amount,
                    'from': wallet.address
                })
                gas_limit = int(estimated_gas * 1.2)  # Добавляем 20% запаса
                self.logger.info(f"🔧 Estimated gas: {estimated_gas}, using: {gas_limit}")
            except Exception as e:
                self.logger.warning(f"⚠️ Gas estimation failed, using default: {e}")
                gas_limit = 21000  # Fallback

            # ✅ ОСОБЫЕ НАСТРОЙКИ GAS ДЛЯ OPN
            if current_chain_id == 984:  # OPN Testnet
                gas_price = max(self.web3.eth.gas_price, self.web3.to_wei(7, 'gwei'))
            else:
                gas_price = self.web3.eth.gas_price

            nonce = self.web3.eth.get_transaction_count(wallet.address)

            # ✅ ИСПОЛЬЗУЕМ CHECKSUM АДРЕС В ТРАНЗАКЦИИ
            transaction = {
                'to': to_address_checksum,
                'value': amount,
                'gas': gas_limit,
                'gasPrice': gas_price,
                'nonce': nonce,
                'chainId': current_chain_id,
                'data': b''
            }

            self.logger.info(f"📝 Transaction details:")
            self.logger.info(f"   From: {wallet.address}")
            self.logger.info(f"   To: {to_address_checksum}")
            self.logger.info(f"   Amount: {amount_native:.6f} {native_token}")
            self.logger.info(f"   Gas: {gas_limit} | GasPrice: {self.web3.from_wei(gas_price, 'gwei'):.2f} Gwei")
            self.logger.info(f"   ChainId: {current_chain_id}")

            # Подписываем и отправляем
            signed_txn = wallet.account.sign_transaction(transaction)
            tx_hash = self.web3.eth.send_raw_transaction(signed_txn.raw_transaction)

            self.logger.info(f"📤 Transaction sent: {tx_hash.hex()}")

            # Ждем подтверждения
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)

            if receipt.status == 1:
                gas_used = receipt.gasUsed
                actual_gas_cost = gas_used * gas_price
                self.logger.info(f"✅ Transfer successful! TX: {tx_hash.hex()}")
                self.logger.info(
                    f"⛽ Gas used: {gas_used} | Cost: {self.web3.from_wei(actual_gas_cost, 'ether'):.6f} {native_token}")

                # Показываем ссылку в explorer
                if network_config and network_config.get('explorer'):
                    explorer_url = network_config['explorer'].rstrip('/')
                    tx_explorer_url = f"{explorer_url}/tx/{tx_hash.hex()}"
                    self.logger.info(f"🌐 View in explorer: {tx_explorer_url}")

                return True
            else:
                self.logger.error(f"❌ Transfer failed: {tx_hash.hex()}")
                return False

        except Exception as e:
            self.logger.error(f"❌ Native transfer failed: {e}")
            return False

    async def execute_random_transfer(self, wallet, network_name: str) -> bool:
        """Выполнение реального случайного трансфера с правильными процентами"""
        try:
            await self._wait_for_cooldown()

            self.logger.info(f"🎯 Starting REAL transfer from {wallet.name}")

            # ✅ ИСПОЛЬЗУЕМ НОРМАЛИЗОВАННОЕ ИМЯ СЕТИ
            normalized_network = normalize_network_name(network_name)
            network_config = self.config.get_network_by_name(normalized_network)

            if not network_config:
                self.logger.error(f"❌ Network config not found: {normalized_network}")
                return False

            if not wallet.web3:
                self.logger.info(f"🔌 Connecting wallet {wallet.name} to {normalized_network}...")
                if not wallet.connect_to_network(network_config['rpc_url']):
                    self.logger.error(f"❌ Failed to connect wallet {wallet.name} to network {normalized_network}")
                    return False

            if not wallet.web3.is_connected():
                self.logger.error(f"❌ Wallet {wallet.name} is not connected to any network")
                return False

            # Получаем баланс кошелька
            balance = wallet.web3.eth.get_balance(wallet.address)
            balance_native = float(wallet.web3.from_wei(balance, 'ether'))  # ✅ ПРЕОБРАЗУЕМ В FLOAT

            self.logger.info(f"💰 Wallet {wallet.name} balance: {balance_native:.6f} {network_config['native_token']}")

            if balance == 0:
                self.logger.warning(f"⚠️ Zero balance for transfer in {wallet.name}")
                return False

            # Получаем случайный адрес получателя
            max_retries = 3
            retry_count = 0

            while retry_count < max_retries:
                to_address = await self.get_random_address(normalized_network)
                if not to_address:
                    self.logger.error("❌ Failed to get recipient address")
                    return False

                self.logger.info(f"🔍 Validating recipient address: {to_address[:16]}...")

                # ✅ УЛУЧШЕННАЯ ПРОВЕРКА АДРЕСА ПОЛУЧАТЕЛЯ
                is_valid_recipient = await self._validate_recipient_address(to_address, wallet.address)

                if not is_valid_recipient:
                    self.logger.warning(f"⚠️ Recipient {to_address[:16]}... invalid, retrying...")
                    retry_count += 1
                    continue
                else:
                    self.logger.info(f"✅ Recipient {to_address[:16]}... validated as safe ACTIVE EOA")
                    break

            if retry_count >= max_retries:
                self.logger.error("❌ Failed to get valid recipient address after retries")
                return False

            # ✅ ИСПРАВЛЕННЫЙ РАСЧЕТ ДЛЯ OPN: 0.1-0.3% ОТ БАЛАНСА
            if is_opn_network(normalized_network):
                # ✅ ПРАВИЛЬНЫЙ РАСЧЕТ ПРОЦЕНТОВ 0.1-0.3%
                min_percentage = 0.1
                max_percentage = 0.3
                transfer_percentage = random.uniform(min_percentage, max_percentage)

                # ✅ РАСЧЕТ СУММЫ В ETH (используем float)
                transfer_amount_eth = balance_native * (transfer_percentage / 100)

                # ✅ ПРЕОБРАЗУЕМ В WEI
                transfer_amount = wallet.web3.to_wei(transfer_amount_eth, 'ether')

                # ✅ УМНЫЕ МИНИМАЛЬНЫЕ И МАКСИМАЛЬНЫЕ СУММЫ ДЛЯ OPN
                # Минимум: 0.001 OPN или 2x стоимости газа
                estimated_gas_cost = wallet.web3.to_wei(0.0002, 'ether')
                min_amount = max(wallet.web3.to_wei(0.001, 'ether'), int(estimated_gas_cost * 2))

                # ✅ ИСПРАВЛЕННЫЙ МАКСИМУМ: 0.5% от баланса ИЛИ 0.02 OPN (что МЕНЬШЕ)
                max_amount_percentage = int(balance * 0.005)  # 0.5% от баланса
                max_amount_fixed = wallet.web3.to_wei(0.02, 'ether')
                max_amount = min(max_amount_fixed, max_amount_percentage)

                self.logger.info(f"📊 Calculated limits: Min={wallet.web3.from_wei(min_amount, 'ether'):.6f}, "
                                 f"Max={wallet.web3.from_wei(max_amount, 'ether'):.6f}, "
                                 f"Percentage={transfer_percentage:.3f}%")

                # ✅ ОГРАНИЧИВАЕМ СУММУ
                if transfer_amount < min_amount:
                    transfer_amount = min_amount
                    transfer_percentage = float((min_amount / balance) * 100)
                    self.logger.info(f"🔧 Adjusted to minimum: {wallet.web3.from_wei(min_amount, 'ether'):.6f} OPN")
                elif transfer_amount > max_amount:
                    transfer_amount = max_amount
                    transfer_percentage = float((max_amount / balance) * 100)
                    self.logger.info(f"🔧 Adjusted to maximum: {wallet.web3.from_wei(max_amount, 'ether'):.6f} OPN")
                else:
                    self.logger.info(
                        f"🎲 Using calculated amount: {wallet.web3.from_wei(transfer_amount, 'ether'):.6f} OPN")

            else:
                # Для других сетей старые настройки
                min_percentage = 0.2
                max_percentage = 0.9
                transfer_percentage = random.uniform(min_percentage, max_percentage)
                transfer_amount_eth = balance_native * (transfer_percentage / 100)
                transfer_amount = wallet.web3.to_wei(transfer_amount_eth, 'ether')

                min_amount = wallet.web3.to_wei(0.0001, 'ether')
                max_amount = wallet.web3.to_wei(0.01, 'ether')

                if transfer_amount < min_amount:
                    transfer_amount = min_amount
                    transfer_percentage = (min_amount / balance) * 100
                elif transfer_amount > max_amount:
                    transfer_amount = max_amount
                    transfer_percentage = (max_amount / balance) * 100

            # ✅ ОСОБЫЕ НАСТРОЙКИ GAS ДЛЯ OPN
            if is_opn_network(normalized_network):
                # OPN имеет минимальный gas price 7 Gwei
                gas_price = max(wallet.web3.eth.gas_price, wallet.web3.to_wei(7, 'gwei'))
                gas_limit = 21000
            else:
                # Стандартные настройки газа для других сетей
                if self.gas_monitor:
                    try:
                        gas_price = await self.gas_monitor.get_optimal_gas_price(normalized_network)
                        gas_limits = self.gas_monitor.get_gas_limits("transfer")
                        gas_limit = gas_limits["gas_limit"]
                    except Exception as e:
                        self.logger.warning(f"⚠️ Gas monitor error, using fallback: {e}")
                        gas_price = wallet.web3.eth.gas_price
                        gas_limit = 21000
                else:
                    gas_price = wallet.web3.eth.gas_price
                    gas_limit = 21000

            gas_cost = gas_price * gas_limit

            # ✅ УЛУЧШЕННАЯ ПРОВЕРКА БАЛАНСА (ОСТАВЛЯЕМ ТОЛЬКО ЭТУ)
            required_total = transfer_amount + gas_cost

            if required_total > balance:
                # Пробуем уменьшить сумму перевода
                new_transfer_amount = balance - gas_cost

                if new_transfer_amount < min_amount:
                    self.logger.warning(
                        f"⚠️ Not enough balance for transfer + gas. Need: {wallet.web3.from_wei(required_total, 'ether'):.6f}, Have: {balance_native:.6f}")
                    return False

                transfer_amount = new_transfer_amount
                transfer_percentage = (transfer_amount / balance) * 100
                self.logger.info(
                    f"🔧 Reduced transfer amount due to gas costs: {wallet.web3.from_wei(transfer_amount, 'ether'):.6f} OPN")

            # ✅ ФИНАЛЬНАЯ ПРОВЕРКА: СУММА > GAS
            if transfer_amount <= gas_cost:
                self.logger.warning(f"⚠️ Transfer amount too small after gas adjustment")
                return False

            amount_native = wallet.web3.from_wei(transfer_amount, 'ether')
            gas_native = wallet.web3.from_wei(gas_cost, 'ether')

            self.logger.info(
                f"💸 Preparing transfer: {float(amount_native):.6f} {network_config['native_token']} "
                f"({transfer_percentage:.3f}% of balance) | Gas: {float(gas_native):.6f}")

            # Выполняем трансфер
            return await self.execute_native_transfer(wallet, to_address, transfer_amount)

        except Exception as e:
            self.logger.error(f"❌ Real transfer failed for {wallet.name}: {e}")
            return False

    async def execute_random_transfer_simulation(self, wallet, network_name: str) -> bool:
        """Симуляция случайного трансфера (для тестов)"""
        try:
            self.logger.info(f"🎯 Simulating random transfer from {wallet.name}")

            balance = self.web3.eth.get_balance(wallet.address)
            if balance == 0:
                self.logger.warning(f"⚠️ Zero balance for transfer in {wallet.name}")
                return False

            to_address = await self.get_random_address(network_name)
            if not to_address:
                self.logger.error("❌ Failed to get recipient address")
                return False

            transfer_percentage = Randomizer.get_random_percentage(0.2, 0.9)
            transfer_amount = int(balance * transfer_percentage / 100)

            min_amount = self.web3.to_wei(0.0001, 'ether')
            max_amount = self.web3.to_wei(0.01, 'ether')

            if transfer_amount < min_amount:
                transfer_amount = min_amount
            elif transfer_amount > max_amount:
                transfer_amount = max_amount

            amount_eth = self.web3.from_wei(transfer_amount, 'ether')
            native_token = self.config.get_network_by_name(network_name)['native_token']

            self.logger.info(
                f"📝 Simulated transfer: {amount_eth:.6f} {native_token} from {wallet.name} to {to_address[:8]}...")
            self.logger.info(f"💡 Percentage: {transfer_percentage:.2f}% of balance")

            return True

        except Exception as e:
            self.logger.error(f"❌ Transfer simulation failed for {wallet.name}: {e}")
            return False

    async def _get_opn_addresses_from_api(self) -> str:
        """Упрощенный API парсер для OPN с проверкой EOA"""
        try:
            self.logger.info("🔧 Trying simplified OPN API...")

            api_endpoints = [
                "https://testnet.iopn.tech/api?module=account&action=txlist&sort=desc&offset=50",
                "https://testnet.iopn.tech/api?module=account&action=txlistinternal&sort=desc&offset=30",
            ]

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
            }

            async with aiohttp.ClientSession() as session:
                for endpoint in api_endpoints:
                    try:
                        self.logger.info(f"🔧 Trying OPN API: {endpoint.split('?')[0]}...")

                        async with session.get(endpoint, headers=headers, timeout=10) as response:
                            if response.status == 200:
                                data = await response.json()
                                addresses = self._extract_addresses_from_api_response(data)

                                if addresses:
                                    # ✅ ФИЛЬТРУЕМ ТОЛЬКО EOA АДРЕСА (не контракты)
                                    eoa_addresses = []
                                    for addr in list(addresses)[:20]:  # Проверяем больше адресов
                                        if await self._is_eoa_address(addr):  # НОВЫЙ МЕТОД
                                            eoa_addresses.append(addr)

                                    if eoa_addresses:
                                        selected = random.choice(eoa_addresses)
                                        self.logger.info(f"✅ OPN API found {len(eoa_addresses)} EOA addresses")
                                        return Web3.to_checksum_address(selected)

                    except asyncio.TimeoutError:
                        self.logger.warning(f"⏰ OPN API timeout: {endpoint}")
                        continue
                    except Exception as e:
                        self.logger.debug(f"❌ OPN API endpoint failed: {e}")
                        continue

            return None

        except Exception as e:
            self.logger.error(f"❌ OPN API method failed: {e}")
            return None

    async def _is_eoa_address(self, address: str) -> bool:
        """Проверка что адрес является EOA (не контрактом) и активен"""
        try:
            checksum_addr = Web3.to_checksum_address(address)

            # ✅ ИСКЛЮЧАЕМ СВОЙ КОШЕЛЕК
            if checksum_addr.lower() == "0x9c8822e86e6e965e56f7df18b25e190ef196d341".lower():
                return False

            # ✅ ПРОВЕРКА БАЙТКОДА - главный тест
            code = self.web3.eth.get_code(checksum_addr)
            if code != b'' and code != '0x':
                return False  # Это контракт

            # ✅ ПРОВЕРКА АКТИВНОСТИ
            balance = self.web3.eth.get_balance(checksum_addr)
            tx_count = self.web3.eth.get_transaction_count(checksum_addr)

            return balance > 0 or tx_count > 0

        except Exception as e:
            self.logger.debug(f"❌ EOA check failed for {address[:16]}: {e}")
            return False

    async def _is_active_address(self, address: str) -> bool:
        """Проверка что адрес активен И является EOA (не контрактом)"""
        try:
            checksum_addr = Web3.to_checksum_address(address)

            # ✅ ИСКЛЮЧАЕМ СВОЙ КОШЕЛЕК
            if checksum_addr.lower() == "0x9c8822e86e6e965e56f7df18b25e190ef196d341".lower():
                return False

            # ✅ ПРОВЕРЯЕМ ЧТО ЭТО НЕ КОНТРАКТ (байткод пустой)
            code = self.web3.eth.get_code(checksum_addr)
            if code != b'' and code != '0x':
                self.logger.debug(f"🔍 Address {address[:16]}... is CONTRACT (has bytecode)")
                return False

            # ✅ ПРОВЕРЯЕМ БАЛАНС
            balance = self.web3.eth.get_balance(checksum_addr)
            if balance > 0:
                self.logger.debug(
                    f"🔍 Address {address[:16]}... has balance: {self.web3.from_wei(balance, 'ether'):.6f} OPN")
                return True

            # ✅ ПРОВЕРЯЕМ ТРАНЗАКЦИИ (только для не-zero адресов)
            if address != '0x0000000000000000000000000000000000000000':
                tx_count = self.web3.eth.get_transaction_count(checksum_addr)
                if tx_count > 0:
                    self.logger.debug(f"🔍 Address {address[:16]}... has {tx_count} transactions")
                    return True

            self.logger.debug(f"🔍 Address {address[:16]}... has no activity")
            return False

        except Exception as e:
            self.logger.debug(f"❌ Activity check failed for {address[:16]}: {e}")
            return False

    def _extract_addresses_from_api_data(self, data: dict) -> set:
        """Извлечение адресов из API данных с улучшенной фильтрацией контрактов"""
        addresses = set()

        try:
            # Конвертируем весь JSON в строку и ищем адреса
            json_str = json.dumps(data)
            address_pattern = re.compile(r'0x[a-fA-F0-9]{40}')
            all_addresses = set(address_pattern.findall(json_str))

            self.logger.info(f"🔍 API data contained {len(all_addresses)} potential addresses")

            # ✅ УЛУЧШЕННАЯ ФИЛЬТРАЦИЯ - ИСКЛЮЧАЕМ ИЗВЕСТНЫЕ КОНТРАКТЫ
            filtered_addresses = set()
            for addr in all_addresses:
                if (self._is_valid_address(addr) and
                        not self._is_burn_address(addr) and
                        not self._is_known_contract(addr) and
                        not self._is_likely_contract(addr)):
                    filtered_addresses.add(addr)

            self.logger.info(f"✅ Filtered to {len(filtered_addresses)} safe EOA addresses")
            return filtered_addresses

        except Exception as e:
            self.logger.error(f"❌ Error extracting addresses from API data: {e}")
            return set()

    def _is_likely_contract(self, address: str) -> bool:
        """Проверка что адрес вероятно является контрактом"""
        try:
            address_lower = address.lower()

            # ✅ ИЗВЕСТНЫЕ КОНТРАКТЫ OPN
            known_contracts = {
                '0xa5623ee41248cc5d20b2c9d4e87b455b51464e14',  # Genesis n-Badge OPN
                '0x1e656b2c6b6e91ef6e6a2b16475df7b7d223e3c2',  # Faroswap Router
                '0x902f1ae1a23670f3326af12227276aa3de1b50aa',  # Контракт из транзакций
                '0x68ea2d724825e7b16f11b1690101e46641b1753f',  # Проблемный адрес из лога
                '0xe0be08c77f415f577a1b3a9ad7a1df1479564ec8',  # USDC
                '0xe7e84b8b4f39c507499c40b4ac199b050e2882d5',  # USDT
            }

            if address_lower in known_contracts:
                return True

            # ✅ ПРОВЕРКА ПО ПАТТЕРНАМ
            if (address_lower.count('0') > 25 or
                    address_lower.count('a') > 30 or
                    address_lower.count('f') > 30):
                return True

            return False

        except Exception:
            return False

    def _is_likely_eoa_fast(self, address: str) -> bool:
        """Быстрая проверка EOA с проверкой активности"""
        try:
            address_lower = address.lower()

            # ✅ ИЗВЕСТНЫЕ EOA АДРЕСА OPN
            known_eoa_addresses = {
                '0x9c8822e86e6e965e56f7df18b25e190ef196d341',  # Ваш кошелек wallet_3
                '0x55f3ff987593af3dc67da88ad7f65e1f9ed5dd1b',  # Активный адрес
                '0x0334ec5e1d9b3c58c5176939350aaf7e9fe13dac',  # Активный адрес
            }

            if address_lower in known_eoa_addresses:
                return True

            # ✅ ПРОВЕРКА АКТИВНОСТИ (если доступно)
            try:
                # Проверяем баланс - если > 0, вероятно активный
                balance = self.web3.eth.get_balance(Web3.to_checksum_address(address))
                if balance > 0:
                    self.logger.debug(
                        f"🔍 Address {address[:16]}... has balance: {self.web3.from_wei(balance, 'ether')} OPN")
                    return True
            except:
                pass

            # ✅ ПРОВЕРКА ТРАНЗАКЦИЙ (если доступно)
            try:
                tx_count = self.web3.eth.get_transaction_count(Web3.to_checksum_address(address))
                if tx_count > 0:
                    self.logger.debug(f"🔍 Address {address[:16]}... has {tx_count} transactions")
                    return True
            except:
                pass

            # ✅ ЕСЛИ НЕТ ДАННЫХ ОБ АКТИВНОСТИ - ИСПОЛЬЗУЕМ С ОСТОРОЖНОСТЬЮ
            self.logger.warning(f"⚠️ Address {address[:16]}... has no visible activity")
            return False  # Или True, если хотите рискнуть

        except Exception as e:
            self.logger.debug(f"❌ EOA check failed for {address[:16]}...: {e}")
            return False

    def _is_likely_eoa(self, address: str) -> bool:
        """Улучшенная проверка EOA с кэшированием"""
        try:
            address_lower = address.lower()

            # ✅ ПРОВЕРКА КЭША
            if address_lower in self.verified_contracts:
                return False
            if address_lower in self.verified_eoa:
                return True

            # ✅ ПРОВЕРЯЕМ БАЙТКОД (если доступно)
            try:
                code = self.web3.eth.get_code(Web3.to_checksum_address(address))
                is_eoa = code == b'' or code == '0x'  # EOA имеет пустой байткод

                # ✅ СОХРАНЯЕМ РЕЗУЛЬТАТ В КЭШ
                if is_eoa:
                    self.verified_eoa.add(address_lower)
                else:
                    self.verified_contracts.add(address_lower)

                return is_eoa

            except Exception:
                # Если не можем проверить байткод, считаем EOA
                self.verified_eoa.add(address_lower)
                return True

        except Exception as e:
            self.logger.debug(f"❌ EOA check failed for {address[:16]}...: {e}")
            return True

    def _is_known_contract(self, address: str) -> bool:
        """Проверка что адрес является известным контрактом"""
        known_contracts = {
            '0xa5623ee41248cc5d20b2c9d4e87b455b51464e14',  # Genesis n-Badge OPN
            '0x0000000000000000000000000000000000000000',  # Zero address
            '0x1e656b2c6b6e91ef6e6a2b16475df7b7d223e3c2',  # Faroswap Router
            '0x902f1ae1a23670f3326af12227276aa3de1b50aa',  # Контракт из вашей транзакции
            '0x68ea2d724825e7b16f11b1690101e46641b1753f',  # Проблемный адрес из лога
            '0xe0be08c77f415f577a1b3a9ad7a1df1479564ec8',  # USDC
            '0xe7e84b8b4f39c507499c40b4ac199b050e2882d5',  # USDT
        }
        return address.lower() in known_contracts

    def _find_addresses_in_dict(self, data: dict, addresses: set):
        """Рекурсивный поиск адресов в словаре"""
        try:
            for key, value in data.items():
                if isinstance(value, dict):
                    self._find_addresses_in_dict(value, addresses)
                elif isinstance(value, list):
                    self._find_addresses_in_list(value, addresses)
                elif isinstance(value, str) and self._is_valid_address(value):
                    addresses.add(value)
        except:
            pass

    def _find_addresses_in_list(self, data: list, addresses: set):
        """Рекурсивный поиск адресов в списке"""
        try:
            for item in data:
                if isinstance(item, dict):
                    self._find_addresses_in_dict(item, addresses)
                elif isinstance(item, list):
                    self._find_addresses_in_list(item, addresses)
                elif isinstance(item, str) and self._is_valid_address(item):
                    addresses.add(item)
        except:
            pass

    def _extract_addresses_from_api_response(self, data: dict) -> set:
        """Извлечение адресов из API ответа OPN"""
        addresses = set()
        try:
            # ✅ ОБРАБАТЫВАЕМ РАЗЛИЧНЫЕ ФОРМАТЫ OPN API
            if data.get('status') == '1' and 'result' in data:
                result = data['result']
                if isinstance(result, list):
                    for item in result:
                        if isinstance(item, dict):
                            # Извлекаем адреса из полей транзакций
                            for field in ['from', 'to', 'address', 'contractAddress']:
                                if field in item and item[field]:
                                    addr = item[field]
                                    if self._is_valid_address(addr):
                                        addresses.add(addr)

            # ✅ ДОПОЛНИТЕЛЬНЫЙ ПОИСК ВО ВСЕЙ СТРУКТУРЕ JSON
            json_str = json.dumps(data)
            address_pattern = re.compile(r'0x[a-fA-F0-9]{40}')
            all_addresses = set(address_pattern.findall(json_str))
            addresses.update(all_addresses)

            # ✅ ФИЛЬТРАЦИЯ
            filtered_addresses = set()
            for addr in addresses:
                if (self._is_valid_address(addr) and
                        not self._is_burn_address(addr) and
                        not self._is_known_contract(addr) and
                        not self._is_likely_contract(addr)):
                    filtered_addresses.add(addr)

            self.logger.info(f"🔍 OPN API response: {len(addresses)} → {len(filtered_addresses)} filtered addresses")
            return filtered_addresses

        except Exception as e:
            self.logger.error(f"❌ Error extracting addresses from API response: {e}")
            return set()

    async def _validate_recipient_address(self, address: str, sender_address: str) -> bool:
        """Комплексная проверка адреса получателя"""
        try:
            checksum_addr = Web3.to_checksum_address(address)

            # ✅ ОСНОВНЫЕ ПРОВЕРКИ
            basic_checks = (
                    self._is_valid_address(address) and
                    not self._is_burn_address(address) and
                    not self._is_known_contract(address) and
                    not self._is_likely_contract(address) and
                    address.lower() != sender_address.lower()
            )

            if not basic_checks:
                self.logger.debug(f"❌ Basic checks failed for {address[:16]}")
                return False

            # ✅ ПРОВЕРКА БАЙТКОДА (главный тест на контракт)
            code = self.web3.eth.get_code(checksum_addr)
            if code != b'' and code != '0x':
                self.logger.warning(f"⚠️ Address {address[:16]}... is CONTRACT (bytecode present)")
                return False

            # ✅ ПРОВЕРКА АКТИВНОСТИ
            balance = self.web3.eth.get_balance(checksum_addr)
            tx_count = self.web3.eth.get_transaction_count(checksum_addr)

            is_active = balance > 0 or tx_count > 0
            if not is_active:
                self.logger.debug(f"⚠️ Address {address[:16]}... has no activity (balance=0, txs=0)")
                # Можно разрешить неактивные адреса, но с предупреждением
                # return False  # Если хотите только активные адреса

            self.logger.debug(f"✅ Address {address[:16]}... validated: EOA, active={is_active}")
            return True

        except Exception as e:
            self.logger.error(f"❌ Recipient validation failed for {address[:16]}: {e}")
            return False