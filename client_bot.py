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
from logging.handlers import RotatingFileHandler
import json
import base64

class SatelWifiBot:
    """Clase principal del bot"""
    
    def __init__(self):
        self.bot = telebot.TeleBot(CLIENT_BOT_TOKEN)
        self.mikrotik = MikrotikManager()
        self.db = DatabaseManager()
        self.pending_requests = {}  # Almacenar solicitudes pendientes
        self.user_states = {}  # Almacenar estados de los usuarios
        
        # Configurar logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # Asegurarnos de que el logger tenga handlers
        if not self.logger.handlers:
            # Obtener la ruta del directorio actual
            log_dir = os.path.dirname(os.path.abspath(__file__))
            
            # Handler para archivo
            file_handler = logging.FileHandler(os.path.join(log_dir, 'client_bot.log'))
            file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(file_handler)
            
            # Handler para consola
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(console_handler)
        
        self.logger.info("Bot inicializado")
        
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
            markup.row("👥 Usuarios Activos")
            markup.row("📝 Solicitudes Pendientes", "🎫 Generar Ticket")
            markup.row("ℹ️ Información")
        else:
            markup.row("🎫 Solicitar Ticket")
            markup.row("ℹ️ Información")
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
            
            # Intentar enviar el mensaje
            return self.bot.send_message(
                chat_id,
                text,
                reply_to_message_id=reply_to_message_id,
                parse_mode='HTML',
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
                        "🎫 Solicitar Ticket - Comprar nuevo ticket\n"
                        "ℹ️ Información - Ver precios y planes",
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
                
                # Crear mensaje y markup
                text = self.mikrotik.format_active_users(users)
                markup = types.InlineKeyboardMarkup(row_width=1)
                
                # Agregar botón de eliminar para cada usuario activo
                buttons_added = False
                for user in users:
                    if user['user'] != 'default-trial':  # Permitir eliminar usuarios inactivos también
                        button_text = f"❌ Eliminar {user['user']}"
                        callback_data = f"delete_user_{user['user']}"
                        self.logger.info(f"Agregando botón para eliminar usuario: {user['user']}")
                        markup.add(types.InlineKeyboardButton(
                            text=button_text,
                            callback_data=callback_data
                        ))
                        buttons_added = True
                
                if not buttons_added:
                    self.logger.info("No se agregaron botones al markup")
                
                # Enviar mensaje con botones
                try:
                    self.send_message_safe(
                        message.chat.id,
                        text,
                        reply_markup=markup if buttons_added else None,
                        parse_mode='HTML'
                    )
                    self.logger.info("Mensaje enviado con éxito")
                except Exception as e:
                    self.logger.error(f"Error al enviar mensaje: {str(e)}")
                    raise
                
                self.logger.info(f"Lista de usuarios activos mostrada a {message.from_user.username}")
                
            except Exception as e:
                self.logger.error(f"Error mostrando usuarios activos: {str(e)}")
                self.reply_safe(message, "❌ Error al obtener usuarios activos")
        
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
                            self.bot.send_photo(
                                message.chat.id,
                                request['payment_proof'],
                                caption="🧾 Comprobante de pago"
                            )
                        except Exception as e:
                            self.logger.error(f"Error enviando comprobante de pago: {str(e)}")
                            text += "\n⚠️ Error al cargar comprobante de pago"
                    
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
                
                action, request_id = call.data.split('_', 2)[1:]  # web_approve_123 -> ['web', 'approve', '123']
                self.logger.info(f"Acción web recibida: {action} para solicitud {request_id}")
                
                # Obtener la solicitud de la base de datos
                request_data = self.db.get_request(request_id)
                if not request_data:
                    self.bot.answer_callback_query(call.id, "❌ Solicitud no encontrada.")
                    return
                
                if request_data['status'] != 'pending':
                    self.bot.answer_callback_query(call.id, "❌ Esta solicitud ya fue procesada.")
                    return
                
                if action == 'approve':
                    # Generar ticket
                    ticket = self.generate_ticket()
                    if not ticket:
                        self.bot.answer_callback_query(call.id, "❌ Error generando ticket.")
                        return
                    
                    # Crear usuario en MikroTik
                    duration = f"{request_data['plan_data']['duration']}h"
                    if self.mikrotik.create_user(ticket, ticket, duration):
                        # Actualizar estado en la base de datos
                        self.db.update_request_status(request_id, 'approved', ticket)
                        
                        # Notificar aprobación
                        self.bot.answer_callback_query(call.id, "✅ Solicitud aprobada correctamente.")
                        self.bot.edit_message_text(
                            f"✅ <b>Solicitud Aprobada</b>\n"
                            f"🆔 ID: <code>{request_id}</code>\n"
                            f"👤 Usuario: <code>{request_data['username']}</code>\n"
                            f"🎫 Ticket: <code>{ticket}</code>",
                            call.message.chat.id,
                            call.message.message_id,
                            parse_mode='HTML'
                        )
                        
                    else:
                        self.bot.answer_callback_query(call.id, "❌ Error al crear usuario en MikroTik")
                else:  # reject
                    # Actualizar estado en la base de datos
                    self.db.update_request_status(request_id, 'rejected')
                    
                    # Notificar rechazo
                    self.bot.answer_callback_query(call.id, "❌ Solicitud rechazada.")
                    self.bot.edit_message_text(
                        f"❌ <b>Solicitud Rechazada</b>\n"
                        f"🆔 ID: <code>{request_id}</code>\n"
                        f"👤 Usuario: <code>{request_data['username']}</code>",
                        call.message.chat.id,
                        call.message.message_id,
                        parse_mode='HTML'
                    )
                
            except Exception as e:
                self.logger.error(f"Error procesando acción de solicitud web: {str(e)}")
                self.bot.answer_callback_query(call.id, "❌ Error procesando la solicitud.")
        
        # Generar ticket desde admin
        @self.bot.message_handler(func=lambda message: message.text == "🎫 Generar Ticket" and self.is_admin(message.from_user.id))
        def admin_generate_ticket(message):
            try:
                markup = types.InlineKeyboardMarkup()
                # Agregar opción especial de 10 minutos
                price_10min = round(fixed_price_usd * (10/60), 2)
                price_10min_bs = round(price_10min * exchange_rate, 2)
                btn_text_10min = f"10m - ${price_10min} USD (Bs. {price_10min_bs})"
                markup.add(types.InlineKeyboardButton(btn_text_10min, callback_data="admin_gen_0.167"))
                
                # Agregar planes regulares
                for hours in time_plans:
                    prices = PRICES[f"{hours}h"]
                    btn_text = f"{hours}h - ${prices['usd']} USD (Bs. {prices['bs']})"
                    callback_data = f"admin_gen_{hours}"
                    markup.add(types.InlineKeyboardButton(btn_text, callback_data=callback_data))
                
                self.reply_safe(
                    message,
                    "🎫 Selecciona el tiempo para el ticket:",
                    reply_markup=markup
                )
            except Exception as e:
                self.logger.error(f"Error en admin_generate_ticket: {str(e)}")
                self.reply_safe(message, "❌ Error al mostrar opciones de tiempo. Por favor, intenta nuevamente.")

        # Manejar selección de plan
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('plan_'))
        def handle_plan_selection(call):
            try:
                hours = call.data.split('_')[1]
                prices = PRICES[f"{hours}h"]
                
                message_text = (
                    f"🎫 *Plan Seleccionado*\n"
                    f"⏱ Duración: {hours} horas\n"
                    f"💵 Precio USD: ${prices['usd']}\n"
                    f"💰 Precio Bs: {prices['bs']}\n\n"
                ) + PAYMENT_MESSAGE
                
                self.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=message_text,
                    parse_mode='Markdown'
                )
                
                self.bot.answer_callback_query(call.id)
                
                # Mensaje adicional para instrucciones
                self.send_message_safe(
                    call.message.chat.id,
                    "📤 Por favor, envía una captura de pantalla del comprobante de pago.",
                    reply_markup=types.ForceReply()
                )
                
            except Exception as e:
                self.logger.error(f"Error en handle_plan_selection: {str(e)}")
                self.bot.answer_callback_query(
                    call.id,
                    "❌ Error al procesar selección"
                )
        
        # Manejar comprobantes de pago
        @self.bot.message_handler(content_types=['photo'])
        def handle_payment_proof(message):
            try:
                # Almacenar solicitud pendiente
                self.pending_requests[message.chat.id] = {
                    'username': message.from_user.username or 'Unknown',
                    'photo': message.photo[-1].file_id,  # Guardar el ID de la foto
                    'date': message.date
                }

                # Registrar en el manager
                manager_logger = logging.getLogger('manager')
                manager_logger.info(
                    f"Nueva solicitud de ticket - Usuario: @{message.from_user.username or 'Unknown'} "
                    f"(ID: {message.chat.id})"
                )
                
                # Reenviar a todos los admins
                for admin_id in ADMIN_IDS:
                    try:
                        # Crear botones de acción
                        markup = types.InlineKeyboardMarkup()
                        markup.row(
                            types.InlineKeyboardButton(
                                "✅ Aprobar",
                                callback_data=f"approve_{message.chat.id}"
                            ),
                            types.InlineKeyboardButton(
                                "❌ Rechazar",
                                callback_data=f"reject_{message.chat.id}"
                            )
                        )
                        
                        # Enviar foto y mensaje
                        self.bot.send_photo(
                            admin_id,
                            message.photo[-1].file_id,
                            caption=f"📝 Nueva solicitud de: @{message.from_user.username or 'Unknown'}\n"
                                  f"🆔 Chat ID: {message.chat.id}",
                            reply_markup=markup
                        )
                    except Exception as e:
                        self.logger.error(f"Error al notificar admin {admin_id}: {str(e)}")
                
                # Confirmar al usuario
                self.reply_safe(
                    message,
                    "✅ Comprobante recibido.\n"
                    "Por favor, espera mientras verificamos tu pago.",
                    reply_markup=self.get_user_markup(self.is_admin(message.from_user.id))
                )
            except Exception as e:
                self.logger.error(f"Error en handle_payment_proof: {str(e)}")
                self.reply_safe(
                    message,
                    "❌ Error al procesar comprobante. Por favor, intenta nuevamente.",
                    reply_markup=self.get_user_markup(self.is_admin(message.from_user.id))
                )

        # Manejar aprobación/rechazo de tickets
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'reject_')))
        def handle_ticket_action(call):
            if not self.is_admin(call.from_user.id):
                self.bot.answer_callback_query(call.id, "❌ No tienes permiso para esta acción")
                return
            
            try:
                action = 'approve' if call.data.startswith('approve_') else 'reject'
                request_id = call.data.split('_')[1]
                
                # Verificar si es una solicitud web o de Telegram
                try:
                    user_id = int(request_id)
                    is_web = False
                except ValueError:
                    is_web = True
                
                if is_web:
                    # Manejar solicitud web
                    try:
                        self.logger.info(f"Procesando solicitud web {request_id} - Acción: {action}")
                        
                        # Obtener el path absoluto al archivo de solicitudes
                        requests_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pending_requests.json')
                        
                        # Leer las solicitudes pendientes
                        try:
                            if os.path.exists(requests_file):
                                with open(requests_file, 'r') as f:
                                    web_pending_requests = json.load(f)
                                    self.logger.info(f"Solicitudes pendientes cargadas: {list(web_pending_requests.keys())}")
                            else:
                                self.logger.warning(f"Archivo {requests_file} no existe")
                                web_pending_requests = {}
                        except Exception as e:
                            self.logger.error(f"Error al leer solicitudes: {str(e)}")
                            self.bot.answer_callback_query(call.id, "❌ Error al acceder a las solicitudes")
                            return
                        
                        if request_id not in web_pending_requests:
                            self.logger.warning(f"Solicitud {request_id} no encontrada en pending_requests. Solicitudes disponibles: {list(web_pending_requests.keys())}")
                            self.bot.answer_callback_query(call.id, "❌ La solicitud ya no existe")
                            return

                        request_data = web_pending_requests[request_id]
                        self.logger.info(f"Datos de la solicitud: {request_data}")
                        
                        if action == 'approve':
                            try:
                                # Generar ticket
                                ticket = self.generate_ticket()
                                duration = f"{request_data['plan']['duration']}m"
                                self.logger.info(f"Ticket generado: {ticket}, duración: {duration}")
                                
                                # Crear usuario en MikroTik
                                if self.mikrotik.create_user(ticket, ticket, duration):
                                    try:
                                        # Eliminar la solicitud de web_pending_requests
                                        del web_pending_requests[request_id]
                                        
                                        # Guardar cambios
                                        with open(requests_file, 'w') as f:
                                            json.dump(web_pending_requests, f, indent=2)
                                        
                                        self.logger.info(f"Solicitud {request_id} aprobada y eliminada")
                                        
                                        # Registrar en el manager
                                        manager_logger = logging.getLogger('manager')
                                        manager_logger.info(
                                            f"Ticket web aprobado - Request ID: {request_id} "
                                            f"- Ticket: {ticket} - Admin: @{call.from_user.username or 'Unknown'}"
                                        )

                                        # Actualizar mensaje en Telegram
                                        try:
                                            self.bot.edit_message_text(
                                                chat_id=call.message.chat.id,
                                                message_id=call.message.message_id,
                                                text=f"{call.message.text}\n\n✅ Aprobado por @{call.from_user.username}\nTicket: {ticket}"
                                            )
                                            self.logger.info("Mensaje de Telegram actualizado")
                                        except Exception as e:
                                            self.logger.error(f"Error al actualizar mensaje en Telegram: {str(e)}")
                                            # Si falla la edición del mensaje, intentamos enviar uno nuevo
                                            self.bot.send_message(
                                                call.message.chat.id,
                                                f"✅ Solicitud {request_id} aprobada\nTicket: {ticket}"
                                            )
                                            self.logger.info("Enviado nuevo mensaje de aprobación")
                                        
                                        self.bot.answer_callback_query(call.id, "✅ Solicitud aprobada y ticket creado")
                                    except Exception as e:
                                        self.logger.error(f"Error al actualizar estado: {str(e)}")
                                        self.bot.answer_callback_query(call.id, "✅ Ticket creado pero hubo un error al actualizar el estado")
                                else:
                                    self.logger.error("Error al crear usuario en MikroTik")
                                    self.bot.answer_callback_query(call.id, "❌ Error al crear usuario en MikroTik")
                            except Exception as e:
                                self.logger.error(f"Error al generar ticket: {str(e)}")
                                self.bot.answer_callback_query(call.id, "❌ Error al generar ticket")
                        else:  # reject
                            try:
                                self.logger.info(f"Rechazando solicitud {request_id}")
                                
                                # Eliminar la solicitud de web_pending_requests
                                del web_pending_requests[request_id]
                                
                                # Guardar cambios
                                with open(requests_file, 'w') as f:
                                    json.dump(web_pending_requests, f, indent=2)
                                
                                self.logger.info(f"Solicitud {request_id} rechazada y eliminada")
                                
                                # Actualizar mensaje en Telegram
                                try:
                                    self.bot.edit_message_text(
                                        chat_id=call.message.chat.id,
                                        message_id=call.message.message_id,
                                        text=f"{call.message.text}\n\n❌ Rechazado por @{call.from_user.username}"
                                    )
                                    self.logger.info("Mensaje de Telegram actualizado")
                                except Exception as e:
                                    self.logger.error(f"Error al actualizar mensaje en Telegram: {str(e)}")
                                    # Si falla la edición del mensaje, intentamos enviar uno nuevo
                                    self.bot.send_message(
                                        call.message.chat.id,
                                        f"❌ Solicitud {request_id} rechazada"
                                    )
                                    self.logger.info("Enviado nuevo mensaje de rechazo")
                                
                                # Registrar en el manager
                                manager_logger = logging.getLogger('manager')
                                manager_logger.info(
                                    f"Ticket web rechazado - Request ID: {request_id} "
                                    f"- Admin: @{call.from_user.username or 'Unknown'}"
                                )
                                
                                self.bot.answer_callback_query(call.id, "✅ Solicitud rechazada correctamente")
                            except Exception as e:
                                self.logger.error(f"Error al rechazar solicitud: {str(e)}")
                                self.bot.answer_callback_query(call.id, "❌ Error al rechazar la solicitud")
                    except Exception as e:
                        self.logger.error(f"Error al manejar solicitud web: {str(e)}")
                        self.bot.answer_callback_query(call.id, "❌ Error al procesar solicitud web")
                else:
                    # Manejar solicitud de Telegram
                    if user_id not in self.pending_requests:
                        self.bot.answer_callback_query(call.id, "❌ La solicitud ya no existe")
                        return

                    if action == 'approve':
                        # Generar ticket
                        ticket = self.generate_ticket()
                        duration = "1h"  # Plan por defecto
                        
                        # Crear usuario en MikroTik
                        if self.mikrotik.create_user(ticket, ticket, duration):
                            try:
                                # Registrar en el manager
                                manager_logger = logging.getLogger('manager')
                                manager_logger.info(
                                    f"Ticket aprobado - Usuario: @{self.pending_requests.get(user_id, {}).get('username', 'Unknown')} "
                                    f"(ID: {user_id}) - Ticket: {ticket} - Admin: @{call.from_user.username or 'Unknown'}"
                                )

                                # Enviar ticket al usuario
                                self.send_message_safe(
                                    user_id,
                                    f"✅ Tu solicitud ha sido aprobada!\n\n"
                                    f"Tu ticket es: {ticket}\n\n"
                                    f"Conéctate a la red SatelWifi y usa este ticket como usuario y contraseña."
                                )

                                # Actualizar mensaje en el chat de admin
                                self.bot.edit_message_caption(
                                    chat_id=call.message.chat.id,
                                    message_id=call.message.message_id,
                                    caption=f"{call.message.caption}\n\n✅ Aprobado por @{call.from_user.username}\nTicket: {ticket}"
                                )
                                
                                # Eliminar de pendientes
                                del self.pending_requests[user_id]
                                
                                self.bot.answer_callback_query(call.id, "✅ Ticket enviado al usuario")
                            except Exception as e:
                                self.logger.error(f"Error al aprobar ticket: {str(e)}")
                                self.bot.answer_callback_query(call.id, "❌ Error al enviar ticket")
                        else:
                            self.bot.answer_callback_query(call.id, "❌ Error al crear usuario en MikroTik")
                    else:
                        try:
                            # Enviar mensaje de rechazo al usuario
                            self.send_message_safe(
                                user_id,
                                "❌ Tu solicitud ha sido rechazada.\n"
                                "Por favor, verifica tu comprobante de pago e intenta nuevamente."
                            )
                            
                            # Actualizar mensaje en el chat de admin
                            self.bot.edit_message_caption(
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                caption=f"{call.message.caption}\n\n❌ Rechazado por @{call.from_user.username}"
                            )
                            
                            # Eliminar de pendientes
                            del self.pending_requests[user_id]
                            
                            # Registrar en el manager
                            manager_logger = logging.getLogger('manager')
                            manager_logger.info(
                                f"Ticket rechazado - Usuario: @{self.pending_requests.get(user_id, {}).get('username', 'Unknown')} "
                                f"(ID: {user_id}) - Admin: @{call.from_user.username or 'Unknown'}"
                            )
                            
                            self.bot.answer_callback_query(call.id, "✅ Solicitud rechazada")
                        except Exception as e:
                            self.logger.error(f"Error al rechazar ticket: {str(e)}")
                            self.bot.answer_callback_query(call.id, "❌ Error al rechazar solicitud")
                
            except Exception as e:
                self.logger.error(f"Error en handle_ticket_action: {str(e)}")
                self.bot.answer_callback_query(call.id, "❌ Error al procesar la acción")
        
        # Manejar generación de ticket desde admin
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('admin_gen_'))
        def handle_admin_ticket_generation(call):
            if not self.is_admin(call.from_user.id):
                self.bot.answer_callback_query(call.id, "❌ No tienes permiso para esta acción")
                return
            
            try:
                hours = float(call.data.split('_')[2])
                display_time = f"{int(hours*60)}m" if hours < 1 else f"{hours}h"
                
                # Generar ticket
                ticket = self.generate_ticket()
                
                # Crear usuario en MikroTik
                if self.mikrotik.create_user(ticket, ticket, display_time):
                    # Registrar en el manager
                    manager_logger = logging.getLogger('manager')
                    manager_logger.info(
                        f"Ticket generado por admin - Admin: @{call.from_user.username or 'Unknown'} "
                        f"- Ticket: {ticket} - Tiempo: {display_time}"
                    )

                    # Mostrar ticket al admin
                    self.bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=f"✅ *Ticket generado exitosamente*\n\n"
                             f"🎫 Ticket: `{ticket}`\n"
                             f"⏱ Tiempo: {display_time}\n\n"
                             f"Comparte este ticket con el usuario.",
                        parse_mode='Markdown'
                    )
                else:
                    self.bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text="❌ Error al crear el ticket en MikroTik"
                    )
                
                self.bot.answer_callback_query(call.id)
                
            except Exception as e:
                self.logger.error(f"Error en handle_admin_ticket_generation: {str(e)}")
                self.bot.answer_callback_query(
                    call.id,
                    "❌ Error al generar ticket"
                )
        
        # Manejar eliminación de usuarios
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('delete_user_'))
        def handle_user_deletion(call):
            try:
                # Verificar permisos
                if not self.is_admin(call.from_user.id):
                    self.bot.answer_callback_query(
                        call.id,
                        "⛔️ No tienes permiso para realizar esta acción"
                    )
                    return

                # Obtener username del callback data
                username = call.data.replace('delete_user_', '')
                self.logger.info(f"Intentando eliminar usuario: {username}")
                
                # Intentar eliminar el usuario
                if self.mikrotik.remove_user(username):
                    # Actualizar mensaje con usuarios activos
                    users = self.mikrotik.get_active_users()
                    text = self.mikrotik.format_active_users(users)
                    markup = types.InlineKeyboardMarkup()
                    
                    # Recrear botones para usuarios restantes
                    for user in users:
                        callback_data = f"delete_user_{user['user']}"
                        markup.add(types.InlineKeyboardButton(
                            f"❌ Eliminar {user['user']}", 
                            callback_data=callback_data
                        ))
                    
                    # Actualizar mensaje
                    self.bot.edit_message_text(
                        text,
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=markup,
                        parse_mode='Markdown'
                    )
                    
                    # Notificar éxito
                    self.bot.answer_callback_query(
                        call.id,
                        f"✅ Usuario {username} eliminado correctamente"
                    )
                    self.logger.info(f"Usuario {username} eliminado por {call.from_user.username}")
                else:
                    self.bot.answer_callback_query(
                        call.id,
                        f"❌ No se pudo eliminar el usuario {username}"
                    )
                    self.logger.error(f"Error al eliminar usuario {username}")
            
            except Exception as e:
                self.logger.error(f"Error manejando eliminación de usuario: {str(e)}")
                self.bot.answer_callback_query(
                    call.id,
                    "❌ Error al procesar la solicitud"
                )

        # Manejar acciones de solicitudes web
        @self.bot.callback_query_handler(func=lambda call: call.data and call.data.startswith(('web_approve_', 'web_reject_')))
        def handle_web_request_action(call):
            """Maneja las acciones de aprobar/rechazar solicitudes web"""
            try:
                if not self.is_admin(call.from_user.id):
                    self.bot.answer_callback_query(call.id, "⛔️ No tienes permiso para esta acción")
                    return

                # Extraer acción y request_id del callback_data
                action, _, request_id = call.data.partition('_web_')
                self.logger.info(f"Acción web recibida: {action} para solicitud {request_id}")
                
                # Obtener la solicitud de la base de datos
                request_data = self.db.get_request(request_id)
                if not request_data:
                    self.bot.answer_callback_query(call.id, "❌ Solicitud no encontrada")
                    return
                
                if action == 'approve':
                    # Generar ticket
                    ticket = self.generate_ticket()
                    
                    # Crear usuario en MikroTik
                    plan_data = request_data['plan_data']
                    duration = f"{plan_data['hours']}h"
                    success = self.mikrotik.create_user(ticket, duration)
                    
                    if success:
                        # Actualizar estado en la base de datos
                        self.db.update_request_status(request_id, 'approved', ticket)
                        
                        # Actualizar mensaje original
                        message_text = f"""✅ Solicitud Aprobada
🔑 ID: {request_id}
🎫 Ticket: {ticket}
📦 Plan: {plan_data['name']}
⏱️ Duración: {duration}"""
                        
                        try:
                            # Remover los botones del mensaje original
                            self.bot.edit_message_text(
                                message_text,
                                call.message.chat.id,
                                call.message.message_id,
                                parse_mode='HTML',
                                reply_markup=None
                            )
                        except Exception as e:
                            self.logger.error(f"Error editando mensaje: {str(e)}")
                            # Si no se puede editar, enviar nuevo mensaje
                            self.bot.send_message(call.message.chat.id, message_text)
                        
                        self.bot.answer_callback_query(call.id, "✅ Solicitud aprobada correctamente")
                        self.logger.info(f"Solicitud web {request_id} aprobada - Ticket: {ticket}")
                    else:
                        self.bot.answer_callback_query(call.id, "❌ Error al crear usuario en MikroTik")
                        self.logger.error(f"Error creando usuario en MikroTik para solicitud {request_id}")
                
                elif action == 'reject':
                    # Actualizar estado en la base de datos
                    self.db.update_request_status(request_id, 'rejected')
                    
                    # Actualizar mensaje original
                    message_text = f"""❌ Solicitud Rechazada
🔑 ID: {request_id}
📦 Plan: {request_data['plan_data']['name']}"""
                    
                    try:
                        # Remover los botones del mensaje original
                        self.bot.edit_message_text(
                            message_text,
                            call.message.chat.id,
                            call.message.message_id,
                            parse_mode='HTML',
                            reply_markup=None
                        )
                    except Exception as e:
                        self.logger.error(f"Error editando mensaje: {str(e)}")
                        # Si no se puede editar, enviar nuevo mensaje
                        self.bot.send_message(call.message.chat.id, message_text)
                    
                    self.bot.answer_callback_query(call.id, "✅ Solicitud rechazada")
                    self.logger.info(f"Solicitud web {request_id} rechazada")
                
            except Exception as e:
                self.logger.error(f"Error manejando acción web: {str(e)}")
                self.bot.answer_callback_query(call.id, "❌ Error procesando la acción")
    
    def notify_admins_expired_users(self, expired_users):
        """Notifica a los administradores sobre usuarios cuyo tiempo restante ha expirado"""
        for admin_id in ADMIN_IDS:
            for user in expired_users:
                self.send_message_safe(
                    admin_id,
                    f"⏳ El tiempo del usuario {user['user']} ha expirado.\n"
                    f"Por favor, considera eliminarlo manualmente si no se elimina automáticamente."
                )
    
    def run(self):
        """Inicia el bot"""
        self.logger.info("Iniciando bot...")
        while True:
            try:
                self.bot.polling(none_stop=True, interval=0)
            except Exception as e:
                self.logger.error(f"Error en polling: {str(e)}")
                time.sleep(10)  # Esperar antes de reintentar

if __name__ == "__main__":
    try:
        # Limpiar logs al inicio
        open('client_bot.log', 'w').close()  # Limpiar log del bot
        open('manager.log', 'w').close()     # Limpiar log del manager
        
        logger = logging.getLogger(__name__)
        logger.info("Iniciando bot...")
        bot = SatelWifiBot()
        bot.run()
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error principal: {str(e)}")
