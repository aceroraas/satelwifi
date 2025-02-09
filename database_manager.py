import sqlite3
import logging
import json
from datetime import datetime
from pathlib import Path
from logger_manager import get_logger

class DatabaseManager:
    """Clase para gestionar la base de datos SQLite"""
    
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = Path(__file__).parent / 'satelwifi.db'
        self.db_path = db_path
        self.logger = get_logger('database')
        self.setup_database()
        
    def get_connection(self):
        """Obtiene una conexión a la base de datos"""
        return sqlite3.connect(self.db_path)
    
    def setup_database(self):
        """Crea las tablas necesarias si no existen"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Tabla de solicitudes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS requests (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    timestamp DATETIME NOT NULL,
                    plan_data TEXT NOT NULL,
                    payment_ref TEXT,
                    payment_proof TEXT,
                    source TEXT NOT NULL,
                    chat_id INTEGER,
                    username TEXT,
                    ticket TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Tabla de logs
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    level TEXT NOT NULL,
                    source TEXT NOT NULL,
                    message TEXT NOT NULL,
                    extra_data TEXT
                )
            ''')
            
            # Tabla de usuarios de MikroTik
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS mikrotik_users (
                    username TEXT PRIMARY KEY,
                    password TEXT NOT NULL,
                    duration TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    request_id TEXT,
                    FOREIGN KEY(request_id) REFERENCES requests(id)
                )
            ''')
            
            conn.commit()
    
    def add_request(self, request_id, plan_data, payment_ref=None, payment_proof=None, 
                   source='web', chat_id=None, username=None):
        """Añade una nueva solicitud"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO requests (
                        id, status, timestamp, plan_data, payment_ref, 
                        payment_proof, source, chat_id, username
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    request_id,
                    'pending',
                    datetime.now().isoformat(),
                    json.dumps(plan_data),
                    payment_ref,
                    payment_proof,  # Ahora payment_proof será la ruta del archivo
                    source,
                    chat_id,
                    username
                ))
                conn.commit()
                
                self.log('info', 'database', f'Nueva solicitud añadida: {request_id}')
                return True
        except Exception as e:
            self.log('error', 'database', f'Error al añadir solicitud: {str(e)}')
            return False
    
    def get_pending_requests(self):
        """Obtiene todas las solicitudes pendientes"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, status, plan_data, username, created_at, 
                           payment_ref, payment_proof, source, chat_id
                    FROM requests
                    WHERE status = 'pending'
                    ORDER BY created_at DESC
                ''')
                requests = []
                for row in cursor.fetchall():
                    request = {
                        'id': row[0],
                        'status': row[1],
                        'plan_data': json.loads(row[2]),
                        'username': row[3],
                        'created_at': row[4],
                        'payment_ref': row[5],
                        'payment_proof': row[6],
                        'source': row[7],
                        'chat_id': row[8]
                    }
                    requests.append(request)
                return requests
        except Exception as e:
            self.logger.error(f"Error obteniendo solicitudes pendientes: {str(e)}")
            return []

    def get_request(self, request_id):
        """Obtiene una solicitud específica por su ID"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, status, plan_data, username, created_at, payment_proof, chat_id, ticket
                    FROM requests
                    WHERE id = ?
                ''', (request_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        'id': row[0],
                        'status': row[1],
                        'plan_data': json.loads(row[2]),
                        'username': row[3],
                        'created_at': row[4],
                        'payment_proof': row[5],
                        'chat_id': row[6],
                        'ticket': row[7]
                    }
                return None
        except Exception as e:
            self.logger.error(f"Error obteniendo solicitud {request_id}: {str(e)}")
            return None

    def update_request_status(self, request_id, status, ticket=None):
        """Actualiza el estado de una solicitud"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if ticket:
                    cursor.execute('''
                        UPDATE requests
                        SET status = ?, ticket = ?
                        WHERE id = ?
                    ''', (status, ticket, request_id))
                else:
                    cursor.execute('''
                        UPDATE requests
                        SET status = ?
                        WHERE id = ?
                    ''', (status, request_id))
                conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"Error actualizando estado de solicitud {request_id}: {str(e)}")
            return False

    def add_mikrotik_user(self, username, password, duration, request_id=None):
        """Añade un nuevo usuario de MikroTik"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO mikrotik_users (username, password, duration, request_id)
                    VALUES (?, ?, ?, ?)
                ''', (username, password, duration, request_id))
                conn.commit()
                
                self.log('info', 'database', f'Usuario MikroTik añadido: {username}')
                return True
        except Exception as e:
            self.log('error', 'database', f'Error al añadir usuario MikroTik: {str(e)}')
            return False
    
    def get_mikrotik_user(self, username):
        """Obtiene un usuario de MikroTik por su username"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM mikrotik_users WHERE username = ?
                ''', (username,))
                row = cursor.fetchone()
                
                if row:
                    columns = [desc[0] for desc in cursor.description]
                    return dict(zip(columns, row))
                return None
        except Exception as e:
            self.log('error', 'database', f'Error al obtener usuario MikroTik: {str(e)}')
            return None
    
    def remove_user(self, username):
        """Elimina un usuario de la base de datos"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Primero buscar el request_id asociado al usuario
                cursor.execute('''
                    SELECT request_id 
                    FROM mikrotik_users 
                    WHERE username = ?
                ''', (username,))
                row = cursor.fetchone()
                request_id = row[0] if row else None
                
                # Eliminar el usuario de mikrotik_users
                cursor.execute('''
                    DELETE FROM mikrotik_users 
                    WHERE username = ?
                ''', (username,))
                
                # Si había un request asociado, actualizarlo a 'deleted'
                if request_id:
                    cursor.execute('''
                        UPDATE requests 
                        SET status = 'deleted' 
                        WHERE id = ?
                    ''', (request_id,))
                
                conn.commit()
                self.log('info', 'database', f'Usuario eliminado: {username}')
                return True
        except Exception as e:
            self.log('error', 'database', f'Error al eliminar usuario {username}: {str(e)}')
            return False
    
    def log(self, level, source, message, extra_data=None):
        """Registra un mensaje en el log"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO logs (timestamp, level, source, message, extra_data)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    datetime.now().isoformat(),
                    level,
                    source,
                    message,
                    json.dumps(extra_data) if extra_data else None
                ))
                conn.commit()
        except Exception as e:
            print(f"Error logging to database: {str(e)}")
    
    def get_logs(self, limit=100, level=None, source=None):
        """Obtiene los últimos logs"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                query = '''
                    SELECT * FROM logs
                    WHERE 1=1
                '''
                params = []
                
                if level:
                    query += ' AND level = ?'
                    params.append(level)
                
                if source:
                    query += ' AND source = ?'
                    params.append(source)
                
                query += ' ORDER BY timestamp DESC LIMIT ?'
                params.append(limit)
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                columns = [desc[0] for desc in cursor.description]
                logs = []
                for row in rows:
                    log_data = dict(zip(columns, row))
                    if log_data['extra_data']:
                        log_data['extra_data'] = json.loads(log_data['extra_data'])
                    logs.append(log_data)
                return logs
        except Exception as e:
            self.logger.error(f'Error al obtener logs: {str(e)}')
            return []
