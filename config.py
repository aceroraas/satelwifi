import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración del Bot
CLIENT_BOT_TOKEN = os.getenv('CLIENT_BOT_TOKEN')  # Token del bot
CLIENT_BOT_USERNAME = os.getenv('CLIENT_BOT_USERNAME')  # Username del bot

# Lista de administradores (IDs de Telegram)
ADMIN_IDS = os.getenv('ADMIN_IDS', '').split(',')

# Configuración de MikroTik
MIKROTIK_IP = os.getenv('MIKROTIK_IP')
MIKROTIK_USER = os.getenv('MIKROTIK_USER')
MIKROTIK_PASSWORD = os.getenv('MIKROTIK_PASSWORD')

# Configuración de precios y tasas
exchange_rate = float(os.getenv('EXCHANGE_RATE', '53.85'))  # Tasa de cambio USD a BS
fixed_price_usd = float(os.getenv('FIXED_PRICE_USD', '0.185701021'))  # Precio fijo por hora en USD

# Planes disponibles en horas
time_plans = [1, 2,3, 4, 5,6,12,24]

def calculate_prices():
    """Calcula los precios para cada plan"""
    prices = {}
    for hours in time_plans:
        price_usd = round(fixed_price_usd * hours, 2)
        price_bs = round(price_usd * exchange_rate, 2)
        prices[f"{hours}h" if hours >= 1 else f"{int(hours*60)}m"] = {
            "usd": price_usd,
            "bs": price_bs
        }
    return prices

# Generar precios
PRICES = calculate_prices()

# Configuración de credenciales de administrador
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')

# Configuración de información de pagos
PAYMENT_INFO = {
    'bank_name': os.getenv('BANK_NAME', 'MY BANCO'),
    'account_number': os.getenv('ACCOUNT_NUMBER', '010203XXXX'),
    'payment_methods': ['Pago Móvil', 'Transferencia'],
    'pago_movil_bank_code': os.getenv('PAGO_MOVIL_BANK_CODE', '010X'),
    'pago_movil_identifier': os.getenv('PAGO_MOVIL_IDENTIFIER', 'XXXXXXX'),
    'pago_movil_phone': os.getenv('PAGO_MOVIL_PHONE', 'XXXXX')
}

# Mensaje formateado para mostrar la información de pago
PAYMENT_MESSAGE = """
💳 *Información de Pago*

*Transferencia Bancaria:*
🏦 Banco: {bank_name}
🔢 Número de Cuenta: `{account_number}`

*Pago Móvil:*
🏦 Banco: {bank_name} (Código {pago_movil_bank_code})
📱 Teléfono: `{pago_movil_phone}`
📋 Cédula: `{pago_movil_identifier}`

_Por favor envía el comprobante de pago después de realizar la transferencia._
""".format(**PAYMENT_INFO)
