import logging
import routeros_api
from config import MIKROTIK_IP, MIKROTIK_USER, MIKROTIK_PASSWORD
import re
import traceback
from logger_manager import get_logger
from datetime import datetime

# Usar el nuevo sistema de logging centralizado
logger = get_logger('mikrotik_manager')

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
            if not self.connect():
                return []

            # Obtener usuarios y conexiones activas
            users = self.get_users()
            active_connections = self.get_active_connections()

            # Crear diccionario de conexiones activas
            active_dict = {conn['user']: conn for conn in active_connections}
            formatted_users = []

            for user in users:
                username = user.get('name', '')
                if not username:
                    continue

                # Verificar si el usuario está activo
                is_active = username in active_dict
                uptime = active_dict[username].get('uptime', '0s') if is_active else '0s'

                # Obtener tiempo del ticket
                ticket_time = user.get('limit-uptime', '0s')
                
                # Calcular tiempo restante
                try:
                    total_seconds = self.time_to_seconds(ticket_time)
                    used_seconds = self.time_to_seconds(user.get('uptime', '0s'))
                    remaining_seconds = max(0, total_seconds - used_seconds)
                    time_left = self.seconds_to_readable(remaining_seconds)
                except Exception as e:
                    logger.error(f"Error calculando tiempo para usuario {username}: {str(e)}")
                    time_left = "Error"

                # Intentar obtener el usuario de Telegram
                telegram_user = "Unknown"
                created_at = "Unknown"
                created_by = "Unknown"
                try:
                    if username == 'default-trial':
                        continue
                    
                    if user.get('comment'):
                        telegram_match = re.search(r'user: (@?\w+)', user.get('comment', ''))
                        if telegram_match:
                            telegram_user = f"{telegram_match.group(1)}"
                        create_at_match = re.search(r'created_at: (\d{4}-\d{2}-\d{2})', user.get('comment', ''))
                        if create_at_match:
                            created_at = create_at_match.group(1)
                        created_by_match = re.search(r'created_by: (@?\w+)', user.get('comment', ''))
                        if created_by_match:
                            created_by = created_by_match.group(1)
                except Exception as e:
                    logger.error(f"Error obteniendo usuario de Telegram para {username}: {str(e)}")

                formatted_users.append({
                    'user': username,
                    'telegram': telegram_user,
                    'uptime': ticket_time if 'limit-uptime' in user else '0s',
                    'time_left': time_left,
                    'is_active': is_active,
                    'address': active_dict[username].get('address', 'N/A') if is_active else 'N/A',
                    'id': user.get('.id', ''),
                    'total_time_consumed': uptime if is_active else user.get('uptime', '0s'),
                    'created_at': created_at,
                    'created_by': created_by
                })
            
            return formatted_users
            
        except Exception as e:
            logger.error(f"Error obteniendo usuarios activos: {str(e)}")
            return []
        finally:
            self.disconnect()
    
    
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
    
    def create_user(self, username, password, limit_uptime, userTelegram, createdBy):
        """Crea un nuevo usuario"""
        try:
            if not self.connect():
                logger.error("No se pudo conectar a MikroTik")
                return False

            logger.info(f"Creando usuario {username} con límite de tiempo {limit_uptime}")
            if userTelegram != 'Web': 
                userTelegram = f"@{userTelegram}"
            
            if createdBy != 'Web': 
                createdBy = f"@{createdBy}"

            comment=f"user: {userTelegram} created_at: {datetime.now().strftime('%Y-%m-%d')} created_by: {createdBy}"
            self.api.get_resource("/ip/hotspot/user").add(
                name=username,
                password=password,
                limit_uptime=limit_uptime,
                profile="5M",  # Asignar perfil 5M a todos los usuarios
                comment=comment
            )
            logger.info(f"Usuario {username} creado con perfil 5M y comentario {comment}")
            return True
        except Exception as e:
            logger.error(f"Error creando usuario: {str(e)}\n{traceback.format_exc()}")
            return False
        finally:
            self.disconnect()

    def time_to_seconds(self, time_str):
        """Convierte una cadena de tiempo en segundos"""
        time_units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        return sum(int(num) * time_units[unit] for num, unit in re.findall(r'(\d+)([smhd])', time_str))

    def seconds_to_readable(self, seconds):
        """Convierte segundos a un formato legible"""
        periods = [
            ('día', 86400),
            ('hora', 3600),
            ('minuto', 60),
            ('segundo', 1)
        ]
        parts = []
        for period_name, period_seconds in periods:
            if seconds >= period_seconds:
                period_value, seconds = divmod(seconds, period_seconds)
                parts.append(f"{period_value} {period_name}{'s' if period_value > 1 else ''}")
        return ', '.join(parts)
