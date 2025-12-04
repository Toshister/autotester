# ✅ УНИФИЦИРОВАННЫЕ НАЗВАНИЯ СЕТЕЙ
NETWORK_NAMES = {
    'PHAROS': ['pharos', 'pharos atlantic', 'Pharos Atlantic'],
    'RISE': ['rise', 'rise testnet', 'Rise Testnet'],
    'OPN': ['opn', 'opn testnet', 'OPN Testnet'],
    'ARC': ['arc', 'arc testnet', 'Arc Testnet']
}


def normalize_network_name(network_name: str) -> str:
    """✅ НОРМАЛИЗАЦИЯ НАЗВАНИЯ СЕТИ ДЛЯ СРАВНЕНИЯ"""
    if not network_name:
        return ""

    normalized = network_name.lower().strip()

    # Проверяем Pharos
    if any(pharos_name in normalized for pharos_name in ['pharos', 'atlantic']):
        return 'Pharos Atlantic'

    # Проверяем Rise
    if any(rise_name in normalized for rise_name in ['rise']):
        return 'Rise Testnet'

    # ✅ ПРОВЕРЯЕМ OPN - ДОБАВЛЯЕМ БОЛЕЕ ШИРОКИЕ УСЛОВИЯ
    if any(opn_name in normalized for opn_name in ['opn', 'iopn']):
        return 'OPN Testnet'

    # ✅ ПРОВЕРЯЕМ ARC
    if any(arc_name in normalized for arc_name in ['arc']):
        return 'Arc Testnet'

    # Если не нашли, возвращаем оригинал
    return network_name


def is_pharos_network(network_name: str) -> bool:
    """✅ ПРОВЕРКА ЧТО СЕТЬ - PHAROS"""
    normalized = normalize_network_name(network_name)
    return normalized == 'Pharos Atlantic'


def is_rise_network(network_name: str) -> bool:
    """✅ ПРОВЕРКА ЧТО СЕТЬ - RISE"""
    normalized = normalize_network_name(network_name)
    return normalized == 'Rise Testnet'


def is_opn_network(network_name: str) -> bool:
    """✅ ПРОВЕРКА ЧТО СЕТЬ - OPN"""
    normalized = normalize_network_name(network_name)
    return normalized == 'OPN Testnet'


def is_arc_network(network_name: str) -> bool:
    """✅ ПРОВЕРКА ЧТО СЕТЬ - ARC"""
    normalized = normalize_network_name(network_name)
    return normalized == 'Arc Testnet'
