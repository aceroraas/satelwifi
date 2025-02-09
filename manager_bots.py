#!/usr/bin/env python3
import os
import sys
import subprocess
import venv
from pathlib import Path
import time
import signal
import traceback
import re
from datetime import datetime
from logger_manager import get_logger

logger = get_logger('manager_bots')

def setup_virtual_environment():
    """Configura el entorno virtual si no existe y lo activa"""
    venv_path = Path(__file__).parent / "venv"
    
    # Crear entorno virtual si no existe
    if not venv_path.exists():
        logger.info("Creando entorno virtual...")
        venv.create(venv_path, with_pip=True)
    
    # Obtener el path del python del entorno virtual
    if sys.platform == "win32":
        python_path = venv_path / "Scripts" / "python.exe"
    else:
        python_path = venv_path / "bin" / "python"
    
    if not python_path.exists():
        logger.error("Error: No se pudo crear el entorno virtual")
        sys.exit(1)

    # Si no estamos en el entorno virtual, reejecutar el script en él
    if sys.executable != str(python_path):
        logger.info("Activando entorno virtual...")
        subprocess.run([str(python_path), "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.run([str(python_path), "-m", "pip", "install", "-r", "requirements.txt"])
        subprocess.run([str(python_path), "-m", "pip", "install", "python-dotenv"])  # Instalar python-dotenv
        os.execv(str(python_path), [str(python_path)] + sys.argv)
    else:
        # Asegurarse de que python-dotenv esté instalado
        subprocess.run([str(python_path), "-m", "pip", "install", "python-dotenv"])

# Importar ADMIN_IDS después de configurar el entorno virtual
setup_virtual_environment()
from config import ADMIN_IDS  # Eliminar REFRESH_INTERVAL de la importación

# Inicializar el logger centralizado
logger.info("Iniciando Manager Bots")

def kill_existing_processes():
    """Mata los procesos existentes de Python relacionados con el proyecto"""
    try:
        # Obtener el directorio del proyecto
        project_dir = os.path.dirname(os.path.abspath(__file__))
        logger.info(f"Limpiando procesos en {project_dir}")
        
        # Usar pkill para matar procesos específicos
        processes_to_kill = [
            "python.*client_bot.py",
            "python.*run.py",
            "flask"
        ]
        
        for process in processes_to_kill:
            try:
                subprocess.run(['pkill', '-f', process], check=False)
                logger.info(f"Proceso {process} detenido")
            except Exception as e:
                logger.warning(f"Error al detener {process}: {str(e)}")
        
        # Esperar un momento para asegurar que los procesos se detengan
        time.sleep(2)
        logger.info("Limpieza de procesos completada")
    except Exception as e:
        logger.error(f"Error en kill_existing_processes: {str(e)}")

class BotManager:
    """Clase para manejar el bot de Telegram"""
    
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.bot_process = None
        self.web_process = None
        self.should_run = True
        
        # Configurar el manejador de señales
        signal.signal(signal.SIGTERM, self.handle_shutdown)
        signal.signal(signal.SIGINT, self.handle_shutdown)

    def handle_shutdown(self, signum, frame):
        """Maneja el apagado graceful del bot y el servidor web"""
        logger.info("Deteniendo servicios...")
        self.should_run = False
        self.stop_bot()
        self.stop_web()
        logger.info("Servicios detenidos.")
        sys.exit(0)

    def start_bot(self):
        """Inicia el bot de Telegram"""
        try:
            logger.info("Iniciando bot...")
            self.bot_process = subprocess.Popen(
                [sys.executable, 'client_bot.py'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            logger.info("Bot iniciado exitosamente")
        except Exception as e:
            logger.error(f"Error al iniciar el bot: {e}")

    def stop_bot(self):
        """Detiene el proceso del bot"""
        if self.bot_process:
            logger.info("Deteniendo bot...")
            try:
                self.bot_process.terminate()
                try:
                    self.bot_process.wait(timeout=5)
                    logger.info("Bot detenido exitosamente")
                except subprocess.TimeoutExpired:
                    logger.info("No se pudo obtener la salida del proceso, procediendo a terminar")
                    self.bot_process.kill()
                    logger.info("Bot detenido exitosamente")
            except Exception as e:
                logger.error(f"Error al detener el bot: {e}")

    def start_web(self):
        """Inicia el servidor web Flask"""
        try:
            logger.info("Iniciando servidor web...")
            os.chdir(os.path.join(self.base_dir, 'web'))
            self.web_process = subprocess.Popen(
                [sys.executable, 'run.py'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            os.chdir(self.base_dir)
            logger.info("Servidor web iniciado exitosamente")
        except Exception as e:
            logger.error(f"Error al iniciar el servidor web: {e}")
            os.chdir(self.base_dir)

    def stop_web(self):
        """Detiene el servidor web"""
        if self.web_process:
            try:
                self.web_process.terminate()
                try:
                    self.web_process.wait(timeout=5)
                    logger.info("Servidor web detenido")
                except subprocess.TimeoutExpired:
                    self.web_process.kill()
                    logger.info("Servidor web detenido forzosamente")
            except Exception as e:
                logger.error(f"Error al detener el servidor web: {e}")

    def run(self):
        """Ejecuta el manager"""
        logger.info("Iniciando BotManager...")
        
        # Iniciar el bot y el servidor web
        self.start_bot()
        self.start_web()
        
        # Mantener el proceso principal vivo
        try:
            while self.should_run:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Deteniendo BotManager...")
            self.handle_shutdown(None, None)

def main():
    try:
        # Matar procesos existentes
        kill_existing_processes()
        
        # Iniciar el manager
        manager = BotManager()
        manager.run()
    except Exception as e:
        logger.error(f"Error en main: {str(e)}")
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    logger.info("Iniciando Manager Bots")
    main()
