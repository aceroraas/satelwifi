#!/usr/bin/env python3
import os
import sys
import subprocess
import venv
from pathlib import Path
import time
import signal
import logging
from logging.handlers import RotatingFileHandler
import traceback
import re
from datetime import datetime

def setup_virtual_environment():
    """Configura el entorno virtual si no existe y lo activa"""
    venv_path = Path(__file__).parent / "venv"
    
    # Crear entorno virtual si no existe
    if not venv_path.exists():
        print("Creando entorno virtual...")
        venv.create(venv_path, with_pip=True)
    
    # Obtener el path del python del entorno virtual
    if sys.platform == "win32":
        python_path = venv_path / "Scripts" / "python.exe"
    else:
        python_path = venv_path / "bin" / "python"
    
    if not python_path.exists():
        print("Error: No se pudo crear el entorno virtual")
        sys.exit(1)

    # Si no estamos en el entorno virtual, reejecutar el script en él
    if sys.executable != str(python_path):
        print("Activando entorno virtual...")
        subprocess.run([str(python_path), "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.run([str(python_path), "-m", "pip", "install", "-r", "requirements.txt"])
        subprocess.run([str(python_path), "-m", "pip", "install", "python-dotenv"])  # Instalar python-dotenv
        os.execv(str(python_path), [str(python_path)] + sys.argv)
    else:
        # Asegurarse de que python-dotenv esté instalado
        subprocess.run([str(python_path), "-m", "pip", "install", "python-dotenv"])

# Importar ADMIN_IDS después de configurar el entorno virtual
setup_virtual_environment()
from config import ADMIN_IDS, REFRESH_INTERVAL  # Importar REFRESH_INTERVAL

def setup_logging():
    """Configura el sistema de logging unificado"""
    # Crear el formateador para archivo (detallado)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Crear el formateador para consola (simple)
    console_formatter = logging.Formatter('%(message)s')
    
    # Configurar el manejador de archivo
    file_handler = RotatingFileHandler('satelwifi.log', maxBytes=10485760, backupCount=5)
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.INFO)
    
    # Configurar el manejador de consola
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO)
    
    # Configurar el logger raíz
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Configurar loggers específicos con emojis
    logger_configs = {
        'client_bot': {'emoji': '🤖', 'name': 'Bot'},
        'manager': {'emoji': '🛰', 'name': 'Manager'},
        'mikrotik_manager': {'emoji': '📡', 'name': 'MikroTik'},
        '__main__': {'emoji': '🔧', 'name': 'Sistema'}
    }

    class EmojiFilter(logging.Filter):
        def __init__(self, emoji, name):
            self.emoji = emoji
            self.name = name
            super().__init__()

        def filter(self, record):
            record.emoji = self.emoji
            record.component = self.name
            return True

    # Crear formateador para consola con emojis
    emoji_console_formatter = logging.Formatter('%(emoji)s %(component)s: %(message)s')
    console_handler.setFormatter(emoji_console_formatter)

    # Configurar cada logger específico
    for logger_name, config in logger_configs.items():
        logger = logging.getLogger(logger_name)
        logger.addFilter(EmojiFilter(config['emoji'], config['name']))

def move_cursor_up(lines):
    """Mover el cursor hacia arriba n líneas"""
    sys.stdout.write(f"\033[{lines}A")
    sys.stdout.flush()

def clear_lines(lines):
    """Limpiar n líneas desde la posición actual del cursor"""
    for _ in range(lines):
        sys.stdout.write("\033[2K\r")  # Limpiar línea actual
        sys.stdout.write("\033[1A")    # Mover cursor arriba
    sys.stdout.write("\r")             # Volver al inicio
    sys.stdout.flush()

def print_status(users):
    """Imprimir el estado del sistema sin limpiar la pantalla"""
    # Calcular número total de líneas que vamos a imprimir
    total_lines = 6  # Banner y separadores
    if users:
        for user in users:
            total_lines += 5 if user.get('telegram') else 4
            total_lines += 1  # Separador
    else:
        total_lines += 1  # "No hay usuarios activos"
    
    # Limpiar las líneas anteriores
    clear_lines(total_lines)
    
    # Imprimir nueva información
    print("\n=== 🛰 SatelWifi Manager ===")
    print("=" * 50)
    print("\n📊 Estado del Sistema:")
    print("=" * 50)
    
    if users:
        for user in users:
            print(f"👤 Usuario: {user['user']}")
            if user.get('telegram'):
                print(f"📱 Telegram: {user['telegram']}")
            print(f"⏱ Tiempo usado: {user['uptime']}")
            print(f"⏳ Tiempo restante: {user['time_left']}")
            print(f"📍 IP: {user['address']}")
            print("-" * 30)
    else:
        print("No hay usuarios activos")
    
    print("\nPresiona Ctrl+C para salir")
    print("=" * 50)

def print_system_status(users):
    """Imprime el estado del sistema en la consola"""
    os.system('clear')
    print("\n=== 🛰 SatelWifi Manager ===")
    print("=" * 50)
    
    # Mostrar estado del sistema
    print("\n📊 Estado del Sistema:")
    print("=" * 50)
    
    if users:
        for user in users:
            print(f"👤 Usuario: {user['user']}")
            if user.get('telegram'):
                print(f"📱 Telegram: {user['telegram']}")
            print(f"⏱ Tiempo de ticket: {user['uptime']}")
            print(f"⏱ Tiempo consumido: {user['total_time_consumed']}")
            print(f"⏳ Tiempo restante: {user['time_left']}")
            print(f"📍 IP: {user['address']}")
            print("-" * 30)
    else:
        print("No hay usuarios activos")
        print("-" * 30)
    
    print("\n📝 Últimos eventos del sistema:")
    print("=" * 50)
    
    # Mostrar últimos logs
    try:
        with open('satelwifi.log', 'r') as f:
            logs = f.readlines()
            if logs:
                for log in logs[-5:]:
                    print(log.strip())
    except Exception as e:
        pass
    
    print("\nPresiona Ctrl+C para salir")
    print("=" * 50)

class BotManager:
    """Clase para manejar el bot de Telegram"""
    
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.bot_process = None
        self.should_run = True
        self.last_clear_time = time.time()
        self.mikrotik = MikrotikManager()
        self.last_users = set()  # Para trackear cambios en usuarios
        
        # Configurar el manejador de señales
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        signal.signal(signal.SIGINT, self.handle_shutdown)
    
    def handle_shutdown(self, signum, frame):
        """Maneja el apagado graceful del bot"""
        logging.getLogger('manager').info("Recibida señal de apagado. Deteniendo bot...")
        self.should_run = False
        if self.bot_process:
            self.stop_bot()
        sys.exit(0)
    
    def start_bot(self):
        """Inicia el bot de Telegram"""
        try:
            # Construir el comando con el python del venv
            python_path = Path(__file__).parent / "venv" / ("Scripts" if sys.platform == "win32" else "bin") / ("python.exe" if sys.platform == "win32" else "python")
            cmd = [str(python_path), "client_bot.py"]
            
            # Iniciar el proceso
            self.bot_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.base_dir
            )
            
            logging.getLogger('manager').info("Bot iniciado exitosamente")
            return True
            
        except Exception as e:
            error_msg = f"Error iniciando bot: {str(e)}"
            log_error(logging.getLogger('manager'), error_msg)
            return False
    
    def stop_bot(self):
        """Detiene el proceso del bot"""
        try:
            if self.bot_process:
                logging.getLogger('manager').info("Deteniendo bot...")
                try:
                    # Intentar obtener cualquier salida pendiente con más tiempo de espera
                    stdout, stderr = self.bot_process.communicate(timeout=5)
                    if stdout:
                        logging.getLogger('manager').info(f"Últimas líneas de salida:\n{stdout}")
                    if stderr:
                        logging.getLogger('manager').error(f"Últimos errores:\n{stderr}")
                except subprocess.TimeoutExpired:
                    logging.getLogger('manager').warning("No se pudo obtener la salida del proceso, procediendo a terminar")
                
                # Intentar terminar el proceso gracefully
                self.bot_process.terminate()
                try:
                    self.bot_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logging.getLogger('manager').warning("El bot no se detuvo gracefully, forzando cierre...")
                    # Matar cualquier proceso relacionado
                    try:
                        subprocess.run(['pkill', '-f', 'client_bot.py'], check=False)
                    except Exception as e:
                        error_msg = f"Error al matar procesos: {str(e)}"
                        log_error(logging.getLogger('manager'), error_msg)
                    
                    # Forzar cierre del proceso principal
                    self.bot_process.kill()
                    try:
                        self.bot_process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        logging.getLogger('manager').error("No se pudo matar el proceso completamente")
                
                self.bot_process = None
                logging.getLogger('manager').info("Bot detenido exitosamente")
                return True
                
        except Exception as e:
            error_msg = f"Error al detener el bot: {str(e)}\n{traceback.format_exc()}"
            log_error(logging.getLogger('manager'), error_msg)
        return False
    
    def check_bot_status(self):
        """Verifica el estado del bot"""
        if not self.bot_process:
            return False
        
        # Verificar si el proceso sigue vivo
        if self.bot_process.poll() is not None:
            # Intentar obtener cualquier error que causó la detención
            stdout, stderr = self.bot_process.communicate()
            if stderr:
                logging.getLogger('manager').error(f"El bot se detuvo con error:\n{stderr}")
            return False
        
        return True
    
    def check_active_users(self):
        """Verifica y muestra usuarios activos"""
        try:
            # Obtener usuarios activos
            users = self.mikrotik.get_active_users()
            logger = logging.getLogger('manager')
            
            # Convertir usuarios actuales a set para comparación
            current_users = {user['user'] for user in users}
            
            # Detectar cambios
            new_users = current_users - self.last_users
            disconnected_users = self.last_users - current_users
            
            # Registrar cambios en el log
            for user in new_users:
                logger.info(f"Usuario conectado: {user}")
            
            for user in disconnected_users:
                logger.info(f"Usuario desconectado: {user}")
            
            # Actualizar lista de usuarios
            self.last_users = current_users
            
            # Verificar y eliminar usuarios cuyo tiempo restante ha expirado
            expired_users = [user for user in users if user['time_left'] != 'sin límite' and self.mikrotik.time_to_seconds(user['time_left']) <= 0]
            if expired_users:
                self.mikrotik.check_and_remove_expired_users()
                self.notify_admins_expired_users(expired_users)
            
            # Mostrar estado actual
            print_system_status(users)
            
        except Exception as e:
            error_msg = f"Error verificando usuarios activos: {str(e)}"
            log_error(logging.getLogger('manager'), error_msg)

    def notify_admins_expired_users(self, expired_users):
        """Notifica a los administradores sobre usuarios cuyo tiempo restante ha expirado"""
        for admin_id in ADMIN_IDS:
            for user in expired_users:
                self.send_message_safe(
                    admin_id,
                    f"⏳ El tiempo del usuario {user['user']} ha expirado.\n"
                    f"Por favor, considera eliminarlo manualmente si no se elimina automáticamente."
                )

    def send_message_safe(self, chat_id, text, **kwargs):
        """Envía un mensaje de forma segura, manejando errores comunes"""
        try:
            # Aquí deberías implementar la lógica para enviar mensajes a los administradores
            # Por ejemplo, podrías usar un bot de Telegram para enviar mensajes
            # self.bot.send_message(chat_id, text, **kwargs)
            print(f"Mensaje enviado a {chat_id}: {text}")
        except Exception as e:
            logging.getLogger('manager').error(f"Error enviando mensaje: {str(e)}")

    def run(self):
        """Ejecuta el manager"""
        logger = logging.getLogger('manager')
        logger.info("Iniciando BotManager...")
        
        try:
            # Iniciar el bot
            if self.start_bot():
                # Bucle principal
                while self.should_run:
                    try:
                        # Verificar estado del bot
                        if not self.check_bot_status():
                            logger.warning("Bot no responde, intentando reiniciar...")
                            if not self.start_bot():
                                error_msg = "No se pudo reiniciar el bot"
                                log_error(logger, error_msg)
                                break
                        
                        # Verificar y mostrar usuarios activos
                        self.check_active_users()
                        
                        # Esperar el tiempo de refresco antes de actualizar
                        time.sleep(REFRESH_INTERVAL)
                        
                    except Exception as e:
                        error_msg = f"Error en el monitoreo: {str(e)}"
                        log_error(logger, error_msg)
                        time.sleep(REFRESH_INTERVAL)
            else:
                error_msg = "No se pudo iniciar el bot"
                log_error(logger, error_msg)
        except Exception as e:
            error_msg = f"Error en el manager: {str(e)}\n{traceback.format_exc()}"
            log_error(logger, error_msg)
        finally:
            logger.info("Deteniendo BotManager...")
            self.stop_bot()

def log_error(logger, error_msg):
    """Función auxiliar para mostrar y registrar errores"""
    logger.error(error_msg)

def main():
    try:
        manager = BotManager()
        manager.run()
    except Exception as e:
        error_msg = f"Error fatal en el manager: {str(e)}\n{traceback.format_exc()}"
        log_error(logging.getLogger('__main__'), error_msg)
        sys.exit(1)

if __name__ == "__main__":
    # Configurar entorno virtual antes de cualquier importación
    setup_virtual_environment()

    # Configurar sistema de logs
    setup_logging()

    # Importar después de configurar el entorno virtual
    from mikrotik_manager import MikrotikManager

    main()
