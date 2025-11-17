import json
import os
from typing import Dict, List
from utils.input_utils import secure_input
from utils.logger import setup_logger


class NetworkManager:
    def __init__(self, config_path: str = "config/config.json"):
        self.config_path = config_path
        self.logger = setup_logger("NetworkManager")

    def load_config(self) -> dict:
        """Загрузка конфигурации"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"❌ Ошибка загрузки конфига: {e}")
            return {}

    def save_config(self, config: dict):
        """Сохранение конфигурации"""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            self.logger.info("✅ Конфигурация сохранена")
        except Exception as e:
            self.logger.error(f"❌ Ошибка сохранения конфига: {e}")

    def add_network_interactive(self):
        """Интерактивное добавление новой сети"""
        print("\n🌐 Добавление новой EVM сети")
        print("=" * 50)

        config = self.load_config()
        networks = config.get('networks', [])

        # Проверяем существующие имена сетей
        existing_names = [net.get('name', '') for net in networks]
        existing_chain_ids = [net.get('chain_id', 0) for net in networks]

        # Ввод основных данных сети
        print("\n📋 Основные данные сети:")

        # Название сети
        while True:
            name = secure_input("Название сети (например: ethereum, bsc, polygon): ").strip().lower()
            if not name:
                print("❌ Название не может быть пустым")
                continue
            if name in existing_names:
                print("❌ Сеть с таким названием уже существует")
                continue
            break

        # Chain ID
        while True:
            try:
                chain_id = int(secure_input("Chain ID: "))
                if chain_id <= 0:
                    print("❌ Chain ID должен быть положительным числом")
                    continue
                if chain_id in existing_chain_ids:
                    print("❌ Сеть с таким Chain ID уже существует")
                    continue
                break
            except ValueError:
                print("❌ Введите корректный числовой Chain ID")

        # Символ нативной валюты
        native_symbol = secure_input("Символ нативной валюты (например: ETH, BNB, MATIC): ").strip().upper()
        if not native_symbol:
            native_symbol = "ETH"

        # RPC URL
        while True:
            rpc_url = secure_input("RPC URL: ").strip()
            if not rpc_url:
                print("❌ RPC URL не может быть пустым")
                continue
            if not (rpc_url.startswith('http://') or rpc_url.startswith('https://')):
                print("❌ RPC URL должен начинаться с http:// или https://")
                continue
            break

        # Explorer URL (опционально)
        explorer_url = secure_input("URL блок эксплорера (опционально): ").strip()
        if not explorer_url:
            explorer_url = ""

        # WSS URL (опционально)
        wss_url = secure_input("WebSocket URL (опционально): ").strip()
        if not wss_url:
            wss_url = ""

        # Дополнительные параметры
        print("\n📊 Дополнительные параметры:")
        environment = secure_input("Окружение (mainnet/testnet, опционально): ").strip()
        ratelimit = secure_input("Rate limit (опционально, например: 1000/5m): ").strip()
        max_pending_txs = secure_input("Макс. pending транзакций (опционально): ").strip()

        # Создаем объект сети
        new_network = {
            "name": name,
            "chain_id": chain_id,
            "native_token": native_symbol,
            "rpc_url": rpc_url,
            "explorer": explorer_url,
            "wss_url": wss_url
        }

        # Добавляем опциональные поля если они заполнены
        if environment:
            new_network["environment"] = environment
        if ratelimit:
            new_network["ratelimit"] = ratelimit
        if max_pending_txs:
            try:
                new_network["max_pending_txs"] = int(max_pending_txs)
            except ValueError:
                pass

        # Подтверждение
        print("\n📋 Подтверждение данных сети:")
        print(f"   Название: {name}")
        print(f"   Chain ID: {chain_id}")
        print(f"   Нативная валюта: {native_symbol}")
        print(f"   RPC URL: {rpc_url}")
        print(f"   Explorer: {explorer_url or 'Не указан'}")
        print(f"   WebSocket: {wss_url or 'Не указан'}")

        confirm = secure_input("\nДобавить сеть? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Отменено пользователем")
            return False

        # Добавляем сеть в конфиг
        networks.append(new_network)
        config['networks'] = networks

        # Создаем пустой список токенов для новой сети
        if 'tokens' not in config:
            config['tokens'] = {}
        config['tokens'][name] = {
            native_symbol: "0x0000000000000000000000000000000000000000"
        }

        self.save_config(config)

        print(f"\n✅ Сеть '{name}' успешно добавлена!")

        # Предлагаем добавить токены
        add_tokens = secure_input("Хотите добавить токены для этой сети? (y/N): ").strip().lower()
        if add_tokens == 'y':
            self.add_tokens_to_network_interactive(name)

        return True

    def show_networks_info(self):
        """Показать информацию о сетях"""
        config = self.load_config()
        networks = config.get('networks', [])

        print("\n🌐 Существующие сети:")
        print("=" * 60)

        if not networks:
            print("❌ Сетей нет")
            return

        for i, network in enumerate(networks, 1):
            print(f"{i}. {network.get('name', 'unnamed')}")
            print(f"   🔗 Chain ID: {network.get('chain_id', 'N/A')}")
            print(f"   💰 Нативная валюта: {network.get('native_token', 'N/A')}")
            print(f"   🌐 RPC: {network.get('rpc_url', 'N/A')}")
            print(f"   🔍 Explorer: {network.get('explorer', 'Не указан')}")
            print(f"   ⚡ WebSocket: {network.get('wss_url', 'Не указан')}")
            print(f"   🏷️ Окружение: {network.get('environment', 'Не указано')}")

            # Показываем количество токенов
            tokens = config.get('tokens', {}).get(network['name'], {})
            print(f"   🪙 Токены: {len(tokens)}")
            print()

    def edit_network_interactive(self):
        """Редактирование существующей сети"""
        config = self.load_config()
        networks = config.get('networks', [])

        if not networks:
            print("❌ Сетей нет для редактирования")
            return

        print("\n✏️ Редактирование сети")
        print("=" * 40)

        for i, network in enumerate(networks, 1):
            print(f"{i}. {network.get('name', 'unnamed')} (ChainID: {network.get('chain_id', 'N/A')})")

        try:
            choice = int(secure_input("\nВыберите сеть для редактирования: "))
            if not 1 <= choice <= len(networks):
                print("❌ Неверный выбор")
                return

            network = networks[choice - 1]
            print(f"\nРедактирование сети: {network['name']}")

            # Поля для редактирования
            new_rpc = secure_input(f"Новый RPC URL [{network.get('rpc_url', '')}]: ").strip()
            if new_rpc:
                network['rpc_url'] = new_rpc

            new_explorer = secure_input(f"Новый Explorer URL [{network.get('explorer', '')}]: ").strip()
            if new_explorer:
                network['explorer'] = new_explorer

            new_wss = secure_input(f"Новый WebSocket URL [{network.get('wss_url', '')}]: ").strip()
            if new_wss:
                network['wss_url'] = new_wss

            new_env = secure_input(f"Новое окружение [{network.get('environment', '')}]: ").strip()
            if new_env:
                network['environment'] = new_env

            config['networks'] = networks
            self.save_config(config)
            print("✅ Сеть обновлена!")

        except (ValueError, IndexError):
            print("❌ Неверный выбор")

    def add_tokens_to_network_interactive(self, network_name: str = None):
        """Добавление токенов в сеть"""
        config = self.load_config()

        if not network_name:
            networks = config.get('networks', [])
            if not networks:
                print("❌ Сетей нет")
                return

            print("\n🪙 Добавление токенов в сеть")
            print("=" * 40)

            for i, network in enumerate(networks, 1):
                print(f"{i}. {network.get('name', 'unnamed')}")

            try:
                choice = int(secure_input("\nВыберите сеть: "))
                if not 1 <= choice <= len(networks):
                    print("❌ Неверный выбор")
                    return
                network_name = networks[choice - 1]['name']
            except ValueError:
                print("❌ Неверный выбор")
                return

        # Получаем или создаем список токенов для сети
        if 'tokens' not in config:
            config['tokens'] = {}
        if network_name not in config['tokens']:
            config['tokens'][network_name] = {}

        tokens = config['tokens'][network_name]

        print(f"\n📝 Добавление токенов в сеть '{network_name}'")
        print("Текущие токены:")
        for symbol, address in tokens.items():
            print(f"  {symbol}: {address}")

        while True:
            print("\n➕ Добавление нового токена:")
            symbol = secure_input("Символ токена (например: USDC, DAI): ").strip().upper()
            if not symbol:
                print("❌ Символ не может быть пустым")
                continue

            if symbol in tokens:
                print("❌ Токен с таким символом уже существует")
                continue

            address = secure_input("Адрес контракта токена: ").strip()
            if not address:
                print("❌ Адрес не может быть пустым")
                continue

            # Базовая валидация адреса
            if not address.startswith('0x') or len(address) != 42:
                print("⚠️  Предупреждение: Адрес выглядит невалидным")
                confirm = secure_input("Все равно добавить? (y/N): ").strip().lower()
                if confirm != 'y':
                    continue

            tokens[symbol] = address
            print(f"✅ Токен {symbol} добавлен")

            more = secure_input("Добавить еще токен? (y/N): ").strip().lower()
            if more != 'y':
                break

        config['tokens'][network_name] = tokens
        self.save_config(config)
        print("✅ Токены сохранены!")

    def show_tokens_for_network(self, network_name: str = None):
        """Показать токены для сети"""
        config = self.load_config()

        if not network_name:
            networks = config.get('networks', [])
            if not networks:
                print("❌ Сетей нет")
                return

            print("\n🪙 Просмотр токенов сети")
            print("=" * 40)

            for i, network in enumerate(networks, 1):
                print(f"{i}. {network.get('name', 'unnamed')}")

            try:
                choice = int(secure_input("\nВыберите сеть: "))
                if not 1 <= choice <= len(networks):
                    print("❌ Неверный выбор")
                    return
                network_name = networks[choice - 1]['name']
            except ValueError:
                print("❌ Неверный выбор")
                return

        tokens = config.get('tokens', {}).get(network_name, {})

        print(f"\n🪙 Токены сети '{network_name}':")
        print("=" * 50)

        if not tokens:
            print("❌ Токенов нет")
            return

        for symbol, address in tokens.items():
            print(f"  {symbol}: {address}")

    def delete_network_interactive(self):
        """Удаление сети"""
        config = self.load_config()
        networks = config.get('networks', [])

        if not networks:
            print("❌ Сетей нет для удаления")
            return

        print("\n🗑️ Удаление сети")
        print("=" * 40)

        for i, network in enumerate(networks, 1):
            print(f"{i}. {network.get('name', 'unnamed')} (ChainID: {network.get('chain_id', 'N/A')})")

        try:
            choice = int(secure_input("\nВыберите сеть для удаления: "))
            if not 1 <= choice <= len(networks):
                print("❌ Неверный выбор")
                return

            network = networks[choice - 1]
            confirm = secure_input(f"Удалить сеть '{network['name']}'? (y/N): ").strip().lower()

            if confirm == 'y':
                # Удаляем сеть
                del networks[choice - 1]
                config['networks'] = networks

                # Удаляем токены сети
                if network['name'] in config.get('tokens', {}):
                    del config['tokens'][network['name']]

                self.save_config(config)
                print("✅ Сеть удалена!")
            else:
                print("❌ Отменено")

        except (ValueError, IndexError):
            print("❌ Неверный выбор")