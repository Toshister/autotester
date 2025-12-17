# EVM Auto Tester (Arc / OPN / Pharos)

Инструмент для автосвапов и трансферов в тестовых EVM-сетях. Скрипт поднимает кошельки, выбирает маршруты и исполняет операции через `services/swap_service.py`, `core/transaction_engine.py` и `core/wallet_manager.py` с конфигом в `config/config.json`.

- Покрытые кейсы  
  - Arc (chain_id 5042002, native USDC): маршруты Curve (min BRID ≥0.05, TST ≥0.2, rUSDC ≥0.3, EURC/CA4F ≥1.0; USDC→TST/EURC/CA4F <1 — скип), Universal (USDC/WUSDC/SYN/USDT), DeFi router `0x284C5Afc100ad14a458255075324fA0A9dfd66b1` (USDC→{EURC, SRAC, RACS, SACS, KITTY, DOGG} при балансе ≥40, сумма 5–5.5 USDC, minOut ~80%). Выбор маршрута: ~1/3 DeFi, иначе Curve приоритет → Universal fallback; если токен нет ни в Curve, ни в Universal — пропуск. Газ-резерв native→token ~0.05 (to_wei), gas 700k, gasPrice ≥5 gwei.  
  - OPN (chain_id 984): 50/50 OPN→токен и токен→токен/OPN (OPNT, WOPN, tUSDT, tBNB). Газ-резерв native 0.02, native→token 3–7% баланса (precision 3–5), token→token 4–11% (precision 2–5). WOPN wrap/unwrap gas 120k, swaps 500k, gasPrice ≥7 gwei, дедлайн ~1200s.  
  - Pharos Atlantic (chain_id 688689): Bitverse Universal router `0x585fC3b498b1ABA1F0527663789361D3547aFC88`, пары USDT↔WETH, USDT↔WBTC. Диапазоны: USDT 30–80; WETH 0.008–0.025; WBTC 0.00025–0.0012; кап 95% баланса, дедлайн 30m, gas 900000 с EIP-1559, обязательный approve; при ревёрте пробует другую пару.

## Установка

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

## Запуск

- Интерактивный режим (выбор сети/кошельков/количества операций):
  ```bash
  python main.py
  ```
- Быстрая проверка swap-сервиса:
  ```bash
  python -m py_compile services/swap_service.py
  ```
- Диагностика/интеграционные проверки (используют живые RPC из конфига):
  ```bash
  python run_tests.py
  ```

## Пример конфигурации

`config/config.json` (сокращённо, замените ключи/прокси на свои):

```json
{
  "wallets": [
    { "name": "wallet_0", "private_key": "ENCRYPTED_KEY_BASE64", "proxy": null }
  ],
  "networks": [
    {
      "name": "Arc Testnet",
      "rpc_url": "https://rpc.testnet.arc.network",
      "chain_id": 5042002,
      "native_token": "USDC",
      "tokens": {
        "USDC": "0x3600...0000",
        "EURC": "0x89B5...72a",
        "BRID": "0x1863...8d9",
        "TST": "0xb2B6...8e",
        "rUSDC": "0xAAC9...e0",
        "KITTY": "0xe470...3d",
        "DOGG": "0x832F...cb"
      },
      "contracts": {
        "curve_router": "0xff5cb29241f002ffed2eaa224e3e996d24a6e8d1",
        "universal_router": "0xbf4479C07Dc6fdc6dAa764A0ccA06969e894275F",
        "defi_router": "0x284C5Afc100ad14a458255075324fA0A9dfd66b1",
        "permit2": "0x000000000022d473030f116ddee9f6b43ac78ba3"
      }
    }
    // OPN Testnet, Pharos Atlantic и др. сети по аналогии
  ],
  "operations": {
    "min_per_transaction": 1,
    "max_per_transaction": 2,
    "swap_percentage_min": 1.0,
    "swap_percentage_max": 5.0
  }
}
```

## Что на выходе

- Логи операций в `logs/` (создаётся автоматически), включая детали маршрутов/газовых параметров.
- Отладочные HTML-файлы по OPN в корне (`opn_debug_blocks.html`, `opn_debug_txs.html`).
- Интеграционные тесты печатают статус в консоль (работают с реальными RPC из конфига).
