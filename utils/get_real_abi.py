import requests
import json


def get_contract_abi(contract_address):
    """Получение реального ABI контракта с блокэксплорера"""
    url = f"https://atlantic.pharosscan.xyz/api?module=contract&action=getabi&address={contract_address}"

    try:
        response = requests.get(url)
        data = response.json()

        if data['status'] == '1':
            abi = json.loads(data['result'])
            print(f"✅ ABI получен для {contract_address}")
            return abi
        else:
            print(f"❌ Не удалось получить ABI: {data['result']}")
            return None
    except Exception as e:
        print(f"❌ Ошибка получения ABI: {e}")
        return None


# Адрес Faroswap Router
router_address = "0x1E656B2C6B6e91ef6E6A2B16475Df7b7D223e3c2"
abi = get_contract_abi(router_address)

if abi:
    # Сохраняем ABI в файл
    with open('faroswap_router_abi.json', 'w') as f:
        json.dump(abi, f, indent=2)
    print("✅ ABI сохранен в faroswap_router_abi.json")