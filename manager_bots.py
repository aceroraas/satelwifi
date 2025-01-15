#!/usr/bin/env python3
import os
import sys
import subprocess
import venv
from pathlib import Path

def setup_virtual_environment():
    """Configura el entorno virtual si no existe y lo activa"""
    venv_path = Path(__file__).parent / "venv"
    
    # Crear entorno virtual si no existe
    if not venv_path.exists():
        print("🔧 Creando entorno virtual...")
        venv.create(venv_path, with_pip=True)
    
    # Obtener el path del python del entorno virtual
    if sys.platform == "win32":
        python_path = venv_path / "Scripts" / "python.exe"
    else:
        python_path = venv_path / "bin" / "python"
    
    if not python_path.exists():
        print("❌ Error: No se pudo crear el entorno virtual")
        sys.exit(1)

    # Si no estamos en el entorno virtual, reejecutar el script en él
    if sys.executable != str(python_path):
        print("🔄 Activando entorno virtual...")
        subprocess.run([str(python_path), "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.run([str(python_path), "-m", "pip", "install", "-r", "requirements.txt"])
        os.execv(str(python_path), [str(python_path)] + sys.argv)

# Configurar entorno virtual antes de cualquier otra importación
setup_virtual_environment()

# Ahora podemos importar las dependencias
import time
import signal
import logging
import subprocess
import traceback
import re
from datetime import datetime
from logging.handlers import RotatingFileHandler
from mikrotik_manager import MikrotikManager

# Configurar logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Handler para archivo
file_handler = RotatingFileHandler('manager.log', maxBytes=10485760, backupCount=5)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Handler para consola con formato más limpio
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
logger.addHandler(console_handler)

class BotManager:
    """Clase para manejar el bot de Telegram"""
    
    def __init__(self):
        self.bot_process = None
        self.should_run = True
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.mikrotik = MikrotikManager()
        self.last_clear_time = time.time()
        
        # Configurar el manejador de señales
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        signal.signal(signal.SIGINT, self.handle_shutdown)
    
    def handle_shutdown(self, signum, frame):
        """Maneja el apagado graceful del bot"""
        logger.info("Recibida señal de apagado. Deteniendo bot...")
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
            
            logger.info("Bot iniciado exitosamente")
            return True
            
        except Exception as e:
            logger.error(f"Error iniciando bot: {str(e)}")
            return False
    
    def stop_bot(self):
        """Detiene el proceso del bot"""
        try:
            if self.bot_process:
                logger.info("Deteniendo bot...")
                try:
                    # Intentar obtener cualquier salida pendiente con más tiempo de espera
                    stdout, stderr = self.bot_process.communicate(timeout=5)
                    if stdout:
                        logger.info(f"Últimas líneas de salida:\n{stdout}")
                    if stderr:
                        logger.error(f"Últimos errores:\n{stderr}")
                except subprocess.TimeoutExpired:
                    logger.warning("No se pudo obtener la salida del proceso, procediendo a terminar")
                
                # Intentar terminar el proceso gracefully
                self.bot_process.terminate()
                try:
                    self.bot_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning("El bot no se detuvo gracefully, forzando cierre...")
                    # Matar cualquier proceso relacionado
                    try:
                        subprocess.run(['pkill', '-f', 'client_bot.py'], check=False)
                    except Exception as e:
                        logger.error(f"Error al matar procesos: {str(e)}")
                    
                    # Forzar cierre del proceso principal
                    self.bot_process.kill()
                    try:
                        self.bot_process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        logger.error("No se pudo matar el proceso completamente")
                
                self.bot_process = None
                logger.info("Bot detenido exitosamente")
                return True
                
        except Exception as e:
            logger.error(f"Error al detener el bot: {str(e)}\n{traceback.format_exc()}")
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
                logger.error(f"El bot se detuvo con error:\n{stderr}")
            return False
        
        return True
    
    def check_active_users(self):
        """Verifica y muestra los usuarios activos solo si hay cambios"""
        try:
            # Obtener usuarios activos
            users = self.mikrotik.get_active_users()
            
            # Verificar si hay cambios en los logs
            try:
                with open('manager.log', 'r') as f:
                    manager_logs = f.readlines()
                with open('client_bot.log', 'r') as f:
                    bot_logs = f.readlines()
                
                # Usar los últimos logs como parte del hash
                logs_hash = hash(''.join(manager_logs[-10:] + bot_logs[-10:]))
            except Exception as e:
                logger.error(f"Error leyendo logs: {str(e)}")
                logs_hash = 0
            
            # Calcular hash combinado de usuarios y logs
            current_hash = hash(str(users) + str(logs_hash))
            
            # Actualizar si hay cambios
            if current_hash != self.last_users_hash:
                self.last_users_hash = current_hash
                
                # Limpiar pantalla y mostrar banner
                os.system('clear')
                print("\n=== 🛰 SatelWifi Manager ===")
                print("=" * 50)
                
                # Mostrar últimos logs del manager
                print("\n📝 Logs del Manager:")
                print("=" * 50)
                try:
                    with open('manager.log', 'r') as f:
                        logs = f.readlines()
                        for log in logs[-5:]:  # Mostrar últimos 5 logs
                            print(log.strip())
                except Exception as e:
                    print(f"Error leyendo logs del manager: {str(e)}")
                
                # Mostrar últimos logs del client_bot
                print("\n📱 Logs del Bot:")
                print("=" * 50)
                try:
                    with open('client_bot.log', 'r') as f:
                        logs = f.readlines()
                        for log in logs[-5:]:  # Mostrar últimos 5 logs
                            print(log.strip())
                except Exception as e:
                    print(f"Error leyendo logs del bot: {str(e)}")
                
                print("\n" + "=" * 50)
                
                # Mostrar usuarios activos
                print("\n👥 Usuarios del Sistema:")
                print("=" * 50)
                
                if not users:
                    print("\n📭 No hay usuarios activos")
                else:
                    for user in users:
                        status = "🟢" if user['is_active'] else "⚪️"
                        print(f"\n{status} Usuario: {user['user']}")
                        print(f"📱 Telegram: {user['telegram']}")
                        print(f"⏱ Tiempo usado: {user['uptime']}")
                        print(f"⏳ Tiempo restante: {user['time_left']}")
                        print(f"🌐 IP: {user['address']}")
                        print("➖" * 25)
                
                print("\nPresiona Ctrl+C para salir")
                print("=" * 50)
        
        except Exception as e:
            logger.error(f"Error verificando usuarios activos: {str(e)}")

    def check_and_clear_screen(self):
        """Limpia la pantalla cada 5 minutos y muestra los últimos logs"""
        current_time = time.time()
        if current_time - self.last_clear_time > 300:  # 300 segundos = 5 minutos
            os.system('clear')
            print("\n=== 🛰 SatelWifi Manager ===")
            print("=" * 50)
            
            # Mostrar últimos logs
            try:
                print("\n📝 Últimos logs del Manager:")
                print("=" * 50)
                with open('manager.log', 'r') as f:
                    logs = f.readlines()
                    for log in logs[-5:]:
                        print(log.strip())
            except Exception as e:
                print(f"Error leyendo logs del manager: {str(e)}")
            
            try:
                print("\n🤖 Últimos logs del Bot:")
                print("=" * 50)
                with open('client_bot.log', 'r') as f:
                    logs = f.readlines()
                    for log in logs[-5:]:
                        print(log.strip())
            except Exception as e:
                print(f"Error leyendo logs del bot: {str(e)}")
            
            print("\nMonitoreando logs y usuarios...")
            print("Presiona Ctrl+C para salir")
            print("=" * 50)
            
            self.last_clear_time = current_time

    def monitor_bot_output(self):
        """Monitorea la salida del bot"""
        if not self.bot_process:
            return
            
        # Leer la salida del bot
        stdout_line = self.bot_process.stdout.readline() if self.bot_process.stdout else None
        if stdout_line:
            msg = stdout_line.decode('utf-8').strip()
            print(f"🤖 {msg}")  # Mostrar directamente en consola
        
        stderr_line = self.bot_process.stderr.readline() if self.bot_process.stderr else None
        if stderr_line:
            error_msg = stderr_line.decode('utf-8').strip()
            if "Conflict: terminated by other getUpdates request" in error_msg:
                logger.warning("Detectada otra instancia del bot. Deteniendo esta instancia...")
                self.stop_bot()
                sys.exit(1)
            else:
                print(f"❌ Error: {error_msg}")  # Mostrar error en consola

    def run(self):
        """Ejecuta el manager"""
        logger.info("Iniciando BotManager...")
        
        try:
            # Iniciar el bot
            if self.start_bot():
                os.system('clear')
                print("\n=== 🛰 SatelWifi Manager ===")
                print("=" * 50)
                print("\nMonitoreando logs y usuarios...")
                print("Presiona Ctrl+C para salir")
                print("=" * 50 + "\n")
                
                while True:
                    try:
                        # Limpiar pantalla periódicamente
                        self.check_and_clear_screen()
                        
                        # Monitorear salida del bot
                        self.monitor_bot_output()
                        
                        # Pequeña pausa para no consumir CPU
                        time.sleep(0.1)
                        
                    except Exception as e:
                        logger.error(f"Error en el monitoreo: {str(e)}")
                        time.sleep(5)
            else:
                logger.error("No se pudo iniciar el bot")
        except Exception as e:
            logger.error(f"Error en el manager: {str(e)}\n{traceback.format_exc()}")
        finally:
            self.stop_bot()

def main():
    """Función principal"""
    try:
        manager = BotManager()
        manager.run()
    except Exception as e:
        logger.error(f"Error fatal en el manager: {str(e)}\n{traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main()
