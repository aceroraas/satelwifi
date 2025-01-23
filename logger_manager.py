import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
import os

class LoggerManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoggerManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        # Configurar el logger raíz
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # Limpiar cualquier handler existente
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Configurar el formato del log
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Handler para archivo
        log_path = Path(__file__).parent / 'satelwifi.log'
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
        # Handler para consola
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # Handler para base de datos
        db_handler = DatabaseLogHandler()
        db_handler.setFormatter(formatter)
        root_logger.addHandler(db_handler)
        
        self.logger = root_logger
        self._initialized = True
    
    def get_logger(self, name: Optional[str] = None) -> logging.Logger:
        """Obtiene un logger con el nombre especificado"""
        return logging.getLogger(name)

class DatabaseLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.db_path = Path(__file__).parent / 'satelwifi.db'
        self._setup_database()
    
    def _setup_database(self):
        """Configura la tabla de logs en la base de datos"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Eliminar tabla si existe
            cursor.execute('DROP TABLE IF EXISTS system_logs')
            
            # Crear tabla
            cursor.execute('''
                CREATE TABLE system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    logger_name TEXT,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    source TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error al configurar la base de datos: {e}")
    
    def emit(self, record):
        """Guarda el registro en la base de datos"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=20)
            cursor = conn.cursor()
            
            # Mantener solo los últimos 1000 registros
            cursor.execute('''
                DELETE FROM system_logs 
                WHERE id NOT IN (
                    SELECT id FROM system_logs 
                    ORDER BY timestamp DESC 
                    LIMIT 1000
                )
            ''')
            
            # Insertar nuevo registro
            cursor.execute('''
                INSERT INTO system_logs (timestamp, logger_name, level, message, source)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S'),
                record.name or '',
                record.levelname,
                self.format(record),
                f"{record.filename}:{record.lineno}" if hasattr(record, 'filename') else None
            ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error al guardar log en la base de datos: {e}")

def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Obtiene un logger del LoggerManager"""
    logger_manager = LoggerManager()
    return logger_manager.get_logger(name)
