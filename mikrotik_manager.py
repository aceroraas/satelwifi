import logging
import routeros_api
from config import MIKROTIK_IP, MIKROTIK_USER, MIKROTIK_PASSWORD
import re
import traceback

# Configurar logging
logger = logging.getLogger('mikrotik_manager')

# No configuramos handlers aquí porque los heredará del logger raíz

class MikrotikManager:
    """Clase para manejar las operaciones con MikroTik"""
    
    def __init__(self):
        self.connection = None
        self.api = None
    
    def connect(self):
        """Establece conexión con MikroTik"""
        try:
            self.connection = routeros_api.RouterOsApiPool(
                MIKROTIK_IP,
                username=MIKROTIK_USER,
                password=MIKROTIK_PASSWORD,
                plaintext_login=True
            )
            self.api = self.connection.get_api()
            return True
        except Exception as e:
            logger.error(f"Error conectando a MikroTik: {str(e)}")
            return False
    
    def disconnect(self):
        """Cierra la conexión con MikroTik"""
        try:
            if self.connection:
                self.connection.disconnect()
        except Exception as e:
            logger.error(f"Error desconectando de MikroTik: {str(e)}")
    
    def get_users(self):
        """Obtiene lista de usuarios"""
        try:
            return self.api.get_resource("/ip/hotspot/user").get()
        except Exception as e:
            logger.error(f"Error obteniendo usuarios: {str(e)}")
            return []
    
    def get_active_connections(self):
        """Obtiene conexiones activas"""
        try:
            return self.api.get_resource("/ip/hotspot/active").get()
        except Exception as e:
            logger.error(f"Error obteniendo conexiones activas: {str(e)}")
            return []
    
    def get_active_users(self):
        """Obtiene información de usuarios activos"""
        try:
            # Conectar a MikroTik
            self.connect()
            
            # Obtener usuarios y conexiones activas
            users = self.api.get_resource("/ip/hotspot/user").get()
            active_connections = self.api.get_resource("/ip/hotspot/active").get()
            
            # Crear diccionario de conexiones activas para búsqueda rápida
            active_dict = {conn.get('user', ''): conn for conn in active_connections}
            
            # Formatear la respuesta
            formatted_users = []
            for user in users:
                username = user.get('name', '')
                is_active = username in active_dict
                
                # Obtener información de tiempo
                uptime = "0s"
                time_left = user.get('limit-uptime', 'sin límite')
                if is_active:
                    uptime = active_dict[username].get('uptime', '0s')
                
                # Intentar obtener el nombre de usuario de Telegram del log
                telegram_user = "Unknown"
                try:
                    with open('manager.log', 'r') as f:
                        for line in f:
                            if username in line and "Ticket aprobado" in line:
                                match = re.search(r'Usuario: (@\w+)', line)
                                if match:
                                    telegram_user = match.group(1)
                                break
                except Exception as e:
                    logger.error(f"Error leyendo log para usuario {username}: {str(e)}")

                formatted_users.append({
                    'user': username,
                    'telegram': telegram_user,
                    'uptime': uptime,
                    'time_left': time_left,
                    'is_active': is_active,
                    'address': active_dict[username].get('address', 'N/A') if is_active else 'N/A',
                    'id': user.get('.id', '')  # Necesario para el botón de eliminar
                })
            
            return formatted_users
            
        except Exception as e:
            logger.error(f"Error obteniendo usuarios activos: {str(e)}")
            return []
        finally:
            self.disconnect()
    
    def format_active_users(self, users):
        """Formatear lista de usuarios activos para mostrar"""
        if not users:
            return "No hay usuarios activos"
        
        response = "<b>📊 Usuarios Activos</b>\n\n"
        for user in users:
            status = "🟢" if user['is_active'] else "⚪️"
            telegram = user['telegram'] if user['telegram'] != "Unknown" else "No registrado"
            
            response += (
                f"{status} <b>Usuario:</b> <code>{user['user']}</code>\n"
                f"👤 <b>Telegram:</b> {telegram}\n"
                f"⏱ <b>Tiempo:</b> {user['uptime']}\n"
                f"⏳ <b>Restante:</b> {user['time_left']}\n"
                f"📍 <b>IP:</b> {user['address']}\n"
                "••••••••••\n"
            )
        return response
    
    def remove_user(self, username):
        """Elimina un usuario y asegura su desconexión completa"""
        try:
            # Conectar a MikroTik
            if not self.connect():
                logger.error("No se pudo conectar a MikroTik")
                return False
            
            logger.info(f"Iniciando proceso de eliminación para usuario: {username}")
            success = True
            
            # 1. Primero eliminar de la tabla de hosts activos
            try:
                hosts = self.api.get_resource("/ip/hotspot/host")
                host_list = hosts.get(user=username)
                if host_list:
                    for host in host_list:
                        if 'id' in host:
                            hosts.remove(id=host['id'])
                            logger.info(f"Host eliminado para usuario {username}")
                else:
                    logger.info(f"No se encontraron hosts para el usuario {username}")
            except Exception as e:
                logger.warning(f"Error al eliminar host para usuario {username}: {str(e)}")
                success = False
            
            # 2. Luego desconectar de las conexiones activas
            try:
                active = self.api.get_resource("/ip/hotspot/active")
                active_list = active.get(user=username)
                if active_list:
                    for conn in active_list:
                        if 'id' in conn:
                            active.remove(id=conn['id'])
                            logger.info(f"Conexión activa eliminada para usuario {username}")
                else:
                    logger.info(f"No hay conexiones activas para el usuario {username}")
            except Exception as e:
                logger.warning(f"Error al desconectar usuario {username}: {str(e)}")
                success = False
            
            # 3. Finalmente eliminar el usuario
            try:
                users = self.api.get_resource("/ip/hotspot/user")
                user_list = users.get(name=username)
                if user_list:
                    for user in user_list:
                        if 'id' in user:
                            users.remove(id=user['id'])
                            logger.info(f"Usuario {username} eliminado")
                else:
                    logger.warning(f"Usuario {username} no encontrado")
                    success = False
            except Exception as e:
                logger.error(f"Error al eliminar usuario {username}: {str(e)}")
                success = False
            
            return success
            
        except Exception as e:
            logger.error(f"Error eliminando usuario {username}: {str(e)}")
            return False
        finally:
            self.disconnect()
            logger.info(f"Proceso de eliminación finalizado para usuario {username}")
    
    def create_user(self, username, password, limit_uptime):
        """Crea un nuevo usuario"""
        try:
            self.connect()
            self.api.get_resource("/ip/hotspot/user").add(
                name=username,
                password=password,
                limit_uptime=limit_uptime,
                profile="5M"  # Asignar perfil 5M a todos los usuarios
            )
            logger.info(f"Usuario {username} creado con perfil 5M")
            return True
        except Exception as e:
            logger.error(f"Error creando usuario: {str(e)}")
            return False
        finally:
            self.disconnect()
