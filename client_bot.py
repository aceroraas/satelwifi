import telebot
import logging
import sys
import time
import random
import string
import os
from telebot import types
from datetime import datetime
from config import (
    CLIENT_BOT_TOKEN, CLIENT_BOT_USERNAME, ADMIN_IDS, PRICES, time_plans,
    MIKROTIK_IP, MIKROTIK_USER, MIKROTIK_PASSWORD, PAYMENT_MESSAGE, fixed_price_usd, exchange_rate
)
from mikrotik_manager import MikrotikManager
from database_manager import DatabaseManager
import json
import base64
from logger_manager import get_logger

class SatelWifiBot:
    """Clase principal del bot"""
    
    def __init__(self):
        self.bot = telebot.TeleBot(CLIENT_BOT_TOKEN)
        self.mikrotik = MikrotikManager()
        self.db = DatabaseManager()
        self.pending_requests = {}  # Almacenar solicitudes pendientes
        self.user_states = {}  # Almacenar estados de los usuarios
        
        self.logger = get_logger(__name__)
        self.logger.info("Inicializando Bot... m2")
        
        self.setup_handlers()
        
    def generate_ticket(self, length=8):
        """Genera un ticket aleatorio"""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
    
    def is_admin(self, user_id):
        """Verifica si un usuario es administrador"""
        return str(user_id) in ADMIN_IDS
    
    def get_user_markup(self, is_admin):
        """Retorna el markup correspondiente según el tipo de usuario"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        if is_admin:
            markup.row("👥 Usuarios Activos", "👥 Usuarios Inactivos", "👥 Usuarios Sin Tiempo")
            markup.row("📝 Solicitudes Pendientes", "🎫 Generar Ticket")
        else:
            markup.row("🎫 Solicitar Ticket")
        return markup
    
    def send_message_safe(self, chat_id, text, reply_to_message_id=None, **kwargs):
        """Envía un mensaje de forma segura, manejando errores comunes"""
        try:
            # Limpiar el texto de caracteres especiales que puedan causar problemas
            text = text.replace('\0', '')  # Eliminar caracteres nulos
            
            # Asegurarse de que el texto no esté vacío
            if not text.strip():
                text = "Mensaje vacío"
            
            # Asegurarse de que el chat_id es un string o número
            try:
                chat_id = str(chat_id).strip()
            except:
                self.logger.error(f"Chat ID inválido: {chat_id}")
                return None
            
            # Verificar y limpiar el markup si existe
            if 'reply_markup' in kwargs and kwargs['reply_markup'] is not None:
                # Si el markup no tiene botones, establecerlo como None
                if isinstance(kwargs['reply_markup'], types.InlineKeyboardMarkup):
                    if not kwargs['reply_markup'].keyboard:
                        kwargs['reply_markup'] = None
            
            # Manejar parse_mode: si viene en kwargs, usar ese, si no, usar HTML por defecto
            parse_mode = kwargs.pop('parse_mode', 'HTML')
            
            # Intentar enviar el mensaje
            return self.bot.send_message(
                chat_id,
                text,
                reply_to_message_id=reply_to_message_id,
                parse_mode=parse_mode,
                **kwargs
            )
        except telebot.apihelper.ApiException as e:
            error_msg = str(e)
            if "Bad Request" in error_msg and "wrong file identifier" in error_msg:
                # Si hay un error con el identificador de archivo, intentar enviar sin formato
                try:
                    return self.bot.send_message(
                        chat_id,
                        text.replace('<b>', '').replace('</b>', ''),  # Quitar formato HTML
                        reply_to_message_id=reply_to_message_id,
                        **{k: v for k, v in kwargs.items() if k != 'parse_mode'}  # Quitar parse_mode
                    )
                except Exception as inner_e:
                    self.logger.error(f"Error secundario enviando mensaje sin formato: {str(inner_e)}")
                    return None
            else:
                self.logger.error(f"Error de API enviando mensaje: {error_msg}")
                return None
        except Exception as e:
            self.logger.error(f"Error enviando mensaje: {str(e)}")
            return None

    def reply_safe(self, message, text, **kwargs):
        """Responde a un mensaje de forma segura"""
        try:
            return self.bot.reply_to(message, text, **kwargs)
        except Exception as e:
            self.logger.error(f"Error respondiendo mensaje: {str(e)}")
            try:
                # Si falla el reply, intentar enviar un mensaje normal
                return self.send_message_safe(message.chat.id, text, **kwargs)
            except Exception as e:
                self.logger.error(f"Error crítico respondiendo mensaje: {str(e)}")
                return None

    def forward_message_safe(self, chat_id, from_chat_id, message_id):
        """Reenvía un mensaje de forma segura"""
        try:
            return self.bot.forward_message(chat_id, from_chat_id, message_id)
        except Exception as e:
            self.logger.error(f"Error reenviando mensaje: {str(e)}")
            return None

    def setup_handlers(self):
        """Configura los handlers del bot"""
        # Comando start
        @self.bot.message_handler(commands=['start'])
        def send_welcome(message):
            try:
                user_id = message.from_user.id
                self.logger.info(f"Usuario iniciando bot - Chat ID: {message.chat.id} User ID: {user_id} Username: @{message.from_user.username}")
                
                markup = self.get_user_markup(self.is_admin(user_id))
                
                if self.is_admin(user_id):
                    self.reply_safe(
                        message,
                        "🛡️ Panel de Administración\n"
                        "Selecciona una opción:",
                        reply_markup=markup
                    )
                else:
                    self.reply_safe(
                        message,
                        "¡Bienvenido a SATELWIFI! 🛜\n\n"
                        "🎫 Solicitar Ticket - Comprar nuevo ticket",
                        reply_markup=markup
                    )
            except Exception as e:
                self.logger.error(f"Error en send_welcome: {str(e)}")
                self.reply_safe(message, "❌ Error al iniciar. Por favor, intenta nuevamente.")
        
        # Solicitar ticket
        @self.bot.message_handler(func=lambda message: message.text == "🎫 Solicitar Ticket")
        def request_ticket(message):
            try:
                markup = types.InlineKeyboardMarkup()
                for hours in time_plans:
                    prices = PRICES[f"{hours}h"]
                    btn_text = f"{hours}h - ${prices['usd']} USD (Bs. {prices['bs']})"
                    callback_data = f"plan_{hours}"
                    markup.add(types.InlineKeyboardButton(btn_text, callback_data=callback_data))
                
                self.reply_safe(
                    message,
                    "🎫 Selecciona el plan que deseas comprar:",
                    reply_markup=markup
                )
            except Exception as e:
                self.logger.error(f"Error en request_ticket: {str(e)}")
                self.reply_safe(message, "❌ Error al mostrar planes. Por favor, intenta nuevamente.")
        
        # Ver usuarios activos
        @self.bot.message_handler(func=lambda message: message.text == "👥 Usuarios Activos" and self.is_admin(message.from_user.id))
        def show_active_users(message):
            """Muestra los usuarios activos"""
            if not self.is_admin(message.from_user.id):
                self.reply_safe(message, "⛔️ No tienes permiso para usar este comando.")
                return

            try:
                # Obtener usuarios activos
                users = self.mikrotik.get_active_users()
                
                if not users:
                    self.reply_safe(message, "📝 No hay usuarios activos en este momento.")
                    return

                # Crear mensaje con la información de usuarios
                text = "─" * 10 + "\n"
                for user in users:
                    if user.get('user') and user['user'] != 'default-trial':
                        is_active = user.get('is_active', False)
                        uptime = user.get('total_time_consumed', 'N/A')
                        ticket_time = user.get('uptime', 'N/A')
                        created_by=user.get('created_by','N/A')
                        created_at=user.get('created_at','N/A')
                        time_left = user.get('time_left', 'N/A')
                        if is_active:
                            # Ticket
                            text += f"🎫 *Ticket:* `{user['user']}`\n"
                            # Tiempo del ticket y restante
                            text += f"⏱ *Horas:* {ticket_time}\n"
                            # Tiempo de conexión
                            text += f"📡 *Consumido:* {uptime}\n"
                            # Tiempo del ticket y restante
                            text += f"⏳ *Restante:* {time_left}\n"
                            # Fecha de creación
                            text += f"*Fecha:* {created_at}\n"
                            # Aprobado por
                            text += f"*Aprobado:* {created_by}\n"
                            # Separador entre usuarios
                            text += "─" * 10 + "\n"
                # Enviar mensaje con parse_mode markdown para el formato
                self.reply_safe(message, text, parse_mode='Markdown')
            except Exception as e:
                self.logger.error(f"Error mostrando usuarios activos: {str(e)}")
                self.reply_safe(message, "❌ Error al mostrar usuarios activos. Por favor, intenta nuevamente.")

        # Ver usuarios inactivos
        @self.bot.message_handler(func=lambda message: message.text == "👥 Usuarios Inactivos" and self.is_admin(message.from_user.id))
        def show_inactive_users(message):
            """Muestra los usuarios inactivos"""
            if not self.is_admin(message.from_user.id):
                self.reply_safe(message, "⛔️ No tienes permiso para usar este comando.")
                return

            try:
                # Obtener usuarios activos
                users = self.mikrotik.get_active_users()
                
                if not users:
                    self.reply_safe(message, "📝 No hay usuarios activos en este momento.")
                    return

                # Crear mensaje con la información de usuarios
                text = "─" * 10 + "\n"
                for user in users:
                    if user.get('user') and user['user'] != 'default-trial':
                        is_active = user.get('is_active', False)
                        uptime = user.get('total_time_consumed', 'N/A')
                        ticket_time = user.get('uptime', 'N/A')
                        created_by=user.get('created_by','N/A')
                        created_at=user.get('created_at','N/A')
                        time_left = user.get('time_left', 'N/A')
                        if not is_active and ticket_time != uptime:
                            # Ticket
                            text += f"🎫 *Ticket:* `{user['user']}`\n"
                            text += f"⏱ *Horas:* {ticket_time}\n"
                            # Tiempo de conexión
                            text += f"📡 *Consumido:* {uptime}\n"
                            # Tiempo del ticket y restante
                            text += f"⏳ *Restante:* {time_left}\n"
                            # Fecha de creación
                            text += f"*Fecha:* {created_at}\n"
                            # Aprobado por
                            text += f"*Aprobado:* {created_by}\n"
                            # Separador entre usuarios
                            text += "─" * 10 + "\n"
                # Enviar mensaje con parse_mode markdown para el formato
                self.reply_safe(message, text, parse_mode='Markdown')
            except Exception as e:
                self.logger.error(f"Error mostrando usuarios inactivos: {str(e)}")
                self.reply_safe(message, "❌ Error al mostrar usuarios inactivos. Por favor, intenta nuevamente.")

         # Ver usuarios sin tiempo
        @self.bot.message_handler(func=lambda message: message.text == "👥 Usuarios Sin Tiempo" and self.is_admin(message.from_user.id))
        def show_users_without_time(message):
            """Muestra los usuarios sin tiempo"""
            if not self.is_admin(message.from_user.id):
                self.reply_safe(message, "⛔️ No tienes permiso para usar este comando.")
                return

            try:
                # Obtener usuarios activos
                users = self.mikrotik.get_active_users()
                
                if not users:
                    self.reply_safe(message, "📝 No hay usuarios activos en este momento.")
                    return

                # Crear mensaje con la información de usuarios
                text = "─" * 10 + "\n"
                for user in users:
                    if user.get('user') and user['user'] != 'default-trial':
                        is_active = user.get('is_active', False)
                        uptime = user.get('total_time_consumed', 'N/A')
                        ticket_time = user.get('uptime', 'N/A')
                        created_by=user.get('created_by','N/A')
                        created_at=user.get('created_at','N/A')
                        time_left = user.get('time_left', 'N/A')
                        if not is_active and ticket_time == uptime:
                            # Ticket
                            text += f"🎫 *Ticket:* `{user['user']}`\n"
                            text += f"⏱ *Horas:* {ticket_time}\n"
                            # Tiempo de conexión
                            text += f"📡 *Consumido:* {uptime}\n"
                            # Tiempo del ticket y restante
                            text += f"⏳ *Restante:* {time_left}\n"
                            # Fecha de creación
                            text += f"*Fecha:* {created_at}\n"
                            # Aprobado por
                            text += f"*Aprobado:* {created_by}\n"
                            # Separador entre usuarios
                            text += "─" * 10 + "\n"
                # Enviar mensaje con parse_mode markdown para el formato
                self.reply_safe(message, text, parse_mode='Markdown')
            except Exception as e:
                self.logger.error(f"Error mostrando usuarios sin tiempo: {str(e)}")
                self.reply_safe(message, "❌ Error al mostrar usuarios sin tiempo. Por favor, intenta nuevamente.")
        
        # Ver solicitudes pendientes
        @self.bot.message_handler(func=lambda message: message.text == "📝 Solicitudes Pendientes" and self.is_admin(message.from_user.id))
        def show_pending_requests(message):
            """Muestra las solicitudes pendientes"""
            if not self.is_admin(message.from_user.id):
                self.reply_safe(message, "⛔️ No tienes permiso para usar este comando.")
                return
            
            try:
                # Obtener solicitudes pendientes de la base de datos
                requests = self.db.get_pending_requests()
                
                if not requests:
                    self.reply_safe(message, "📝 No hay solicitudes pendientes.")
                    return
                
                # Procesar cada solicitud
                for request in requests:
                    # Crear mensaje con la información de la solicitud
                    text = (
                        f"📝 <b>Nueva Solicitud {request['source'].upper()}</b>\n"
                        f"🆔 ID: <code>{request['id']}</code>\n"
                        f"👤 Usuario: <code>{request['username']}</code>\n"
                        f"⏱ Plan: {request['plan_data']['duration']} horas\n"
                        f"💰 Monto: ${request['plan_data']['price_usd']} USD\n"
                    )
                    
                    # Agregar referencia de pago si existe
                    if request['payment_ref']:
                        text += f"🔖 Ref. Pago: <code>{request['payment_ref']}</code>\n"
                    
                    # Agregar fecha
                    text += f"📅 Fecha: {request['created_at']}\n"
                    
                    # Crear botones para aprobar/rechazar
                    markup = types.InlineKeyboardMarkup()
                    markup.row(
                        types.InlineKeyboardButton("✅ Aprobar", callback_data=f"web_approve_{request['id']}"),
                        types.InlineKeyboardButton("❌ Rechazar", callback_data=f"web_reject_{request['id']}")
                    )
                    
                    # Si hay comprobante de pago, enviar primero la imagen
                    if request['payment_proof']:
                        try:
                            # Verificar que el comprobante no esté vacío
                            if not request['payment_proof'].strip():
                                raise ValueError("Comprobante de pago vacío")
                                
                            self.logger.info(f"Intentando enviar comprobante de pago: {request['payment_proof']}")
                            sent = self.bot.send_photo(
                                message.chat.id,
                                request['payment_proof'],
                                caption="🧾 Comprobante de pago"
                            )
                            if not sent:
                                raise Exception("No se pudo enviar el comprobante")
                        except Exception as e:
                            self.logger.error(f"Error enviando comprobante de pago: {str(e)} - Valor: {request['payment_proof']}")
                            text += "\n⚠️ Error al cargar comprobante de pago. Por favor, revisa el archivo manualmente."
                    
                    # Enviar mensaje con botones
                    self.send_message_safe(
                        message.chat.id,
                        text,
                        reply_markup=markup,
                        parse_mode='HTML'
                    )
            except Exception as e:
                self.logger.error(f"Error mostrando solicitudes pendientes: {str(e)}")
                self.reply_safe(message, "❌ Error al obtener solicitudes pendientes.")

        # Manejar acciones de solicitudes web
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith(('web_approve_', 'web_reject_')))
        def handle_web_request_action(call):
            """Maneja las acciones de aprobar/rechazar solicitudes web"""
            try:
                if not self.is_admin(call.from_user.id):
                    self.bot.answer_callback_query(call.id, "⛔️ No tienes permiso para realizar esta acción.")
                    return
                
                # Extraer acción y request_id del callback_data
                _, action, request_id = call.data.split('_')  # web_approve_123 -> ['web', 'approve', '123']
                self.logger.info(f"Acción web recibida: {action} para solicitud {request_id}")
                
                # Obtener la solicitud de la base de datos
                request_data = self.db.get_request(request_id)
                if not request_data:
                    self.bot.answer_callback_query(call.id, "❌ Solicitud no encontrada.")
                    return
                
                if action == 'approve':
                    # Generar ticket
                    ticket = self.generate_ticket()
                    if not ticket:
                        self.bot.answer_callback_query(call.id, "❌ Error generando ticket.")
                        return
                    
                    # Crear usuario en MikroTik
                    duration_minutes = request_data['plan_data']['duration']
                    duration_hours = duration_minutes / 60
                    duration = f"{duration_hours}h"
                    userTelegram = call.from_user.username if call.from_user.username else call.from_user.id
                    if self.mikrotik.create_user(ticket, ticket, duration,'Web',userTelegram):
                        # Actualizar estado en la base de datos
                        self.db.update_request_status(request_id, 'approved', ticket)
                        
                        # Eliminar el comprobante de pago si existe
                        if request_data.get('payment_proof'):
                            try:
                                proof_path = os.path.join(os.path.dirname(__file__), 'web/backend', request_data['payment_proof'])
                                if os.path.exists(proof_path):
                                    os.remove(proof_path)
                                    self.logger.info(f"Comprobante de pago eliminado: {proof_path}")
                                else:
                                    self.logger.warning(f"Comprobante de pago no encontrado: {proof_path}")
                            except Exception as e:
                                self.logger.error(f'Error eliminando comprobante de pago: {str(e)}')
                        
                        # Actualizar mensaje original
                        message_text = f"""✅ Solicitud Aprobada
🔑 ID: {request_id}
🎫 Ticket: {ticket}"""
                        
                        try:
                            self.bot.edit_message_text(
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                text=message_text,
                                parse_mode='HTML'
                            )
                        except Exception as e:
                            self.logger.error(f"Error actualizando mensaje: {str(e)}")
                        
                        self.bot.answer_callback_query(call.id, "✅ Solicitud aprobada correctamente")
                    else:
                        self.bot.answer_callback_query(call.id, "❌ Error al crear usuario en MikroTik")
                elif action == 'reject':
                    # Actualizar estado en la base de datos
                    self.db.update_request_status(request_id, 'rejected')
                    
                    # Eliminar el comprobante de pago si existe
                    if request_data.get('payment_proof'):
                        try:
                            proof_path = os.path.join(os.path.dirname(__file__), 'web/backend', request_data['payment_proof'])
                            if os.path.exists(proof_path):
                                os.remove(proof_path)
                                self.logger.info(f"Comprobante de pago eliminado: {proof_path}")
                            else:
                                self.logger.warning(f"Comprobante de pago no encontrado: {proof_path}")
                        except Exception as e:
                            self.logger.error(f'Error eliminando comprobante de pago: {str(e)}')
                    
                    # Actualizar mensaje original
                    message_text = f"""❌ Solicitud Rechazada
🔑 ID: {request_id}
📦 Plan: {request_data['plan_data']['name']}"""
                    
                    try:
                        self.bot.edit_message_text(
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                            text=message_text,
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        self.logger.error(f"Error actualizando mensaje: {str(e)}")
                    
                    self.bot.answer_callback_query(call.id, "✅ Solicitud rechazada")
            except Exception as e:
                self.logger.error(f"Error manejando acción web: {str(e)}")
                self.bot.answer_callback_query(call.id, "❌ Error procesando la acción")

        # Generar ticket (admin)
        @self.bot.message_handler(func=lambda message: message.text == "🎫 Generar Ticket" and self.is_admin(message.from_user.id))
        def admin_generate_ticket(message):
            """Permite a los administradores generar tickets manualmente"""
            if not self.is_admin(message.from_user.id):
                self.reply_safe(message, "⛔️ No tienes permiso para usar este comando.")
                return

            try:
                # Crear markup con los planes disponibles
                markup = types.InlineKeyboardMarkup()
                for hours in time_plans:
                    btn_text = f"{hours}h"
                    callback_data = f"admin_gen_{hours}"
                    markup.add(types.InlineKeyboardButton(btn_text, callback_data=callback_data))
                
                self.reply_safe(
                    message,
                    "🎫 Selecciona la duración del ticket a generar:",
                    reply_markup=markup
                )
            except Exception as e:
                self.logger.error(f"Error en admin_generate_ticket: {str(e)}")
                self.reply_safe(message, "❌ Error al mostrar opciones. Por favor, intenta nuevamente.")

        # Callback para generar ticket (admin)
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('admin_gen_'))
        def handle_admin_generate_ticket(call):
            """Maneja la generación de tickets por parte del admin"""
            try:
                if not self.is_admin(call.from_user.id):
                    self.bot.answer_callback_query(call.id, "⛔️ No tienes permiso para realizar esta acción.")
                    return

                # Extraer duración del plan
                _, _, hours = call.data.split('_')  # admin_gen_24 -> ['admin', 'gen', '24']
                duration = f"{hours}h"
                
                # Generar ticket
                ticket = self.generate_ticket()
                
                # Crear usuario en MikroTik
                userTelegram = call.from_user.username if call.from_user.username else call.from_user.id
                userMessage = call.message.chat.username if call.message.chat.username else call.message.chat.id
                if self.mikrotik.create_user(ticket, ticket, duration, userMessage,userTelegram):
                    # Crear mensaje de confirmación
                    message_text = f"""✅ Ticket Generado

🎫 Ticket: <code>{ticket}</code>
⏱ Duración: {duration}
📅 Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
                    
                    try:
                        # Actualizar mensaje original
                        self.bot.edit_message_text(
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                            text=message_text,
                            parse_mode='HTML'
                        )
                        self.bot.answer_callback_query(call.id, "✅ Ticket generado correctamente")
                    except Exception as e:
                        self.logger.error(f"Error actualizando mensaje: {str(e)}")
                        # Si falla la edición, enviar nuevo mensaje
                        self.send_message_safe(call.message.chat.id, message_text, parse_mode='HTML')
                else:
                    self.bot.answer_callback_query(call.id, "❌ Error al crear usuario en MikroTik")
                    self.logger.error("Error al crear usuario en MikroTik")
            except Exception as e:
                self.logger.error(f"Error en handle_admin_generate_ticket: {str(e)}")
                self.bot.answer_callback_query(call.id, "❌ Error al generar ticket")
    
    
    def run(self):
        """Inicia el bot"""
        self.logger.info("Bot Inicializado... m3")
        while True:
            try:
                self.logger.info("Bot Ready Escuchando... m4")
                self.bot.polling(none_stop=True, interval=0)
            except Exception as e:
                self.logger.error(f"Error en polling: {str(e)}")
                time.sleep(10)  # Esperar antes de reintentar

if __name__ == "__main__":
    try:
        logger = get_logger('client_bot')
        logger.info("Obteniendo bot... m1")
        bot = SatelWifiBot()
        bot.run()
    except Exception as e:
        logger.error(f"Error iniciando el bot: {str(e)}")
        logger.error(traceback.format_exc())
        sys.exit(1)
