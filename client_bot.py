import telebot
import logging
import sys
import time
import random
import string
from telebot import types
from datetime import datetime
from config import (
    CLIENT_BOT_TOKEN, CLIENT_BOT_USERNAME, ADMIN_IDS, PRICES, time_plans,
    MIKROTIK_IP, MIKROTIK_USER, MIKROTIK_PASSWORD, PAYMENT_MESSAGE, fixed_price_usd, exchange_rate
)
from mikrotik_manager import MikrotikManager
from logging.handlers import RotatingFileHandler

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler('client_bot.log', maxBytes=10485760, backupCount=5),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Agregar logging para el manager
manager_logger = logging.getLogger('manager')
manager_logger.setLevel(logging.INFO)
manager_handler = RotatingFileHandler('manager.log', maxBytes=10485760, backupCount=5)
manager_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
manager_logger.addHandler(manager_handler)

class SatelWifiBot:
    """Clase principal del bot"""
    
    def __init__(self):
        self.bot = telebot.TeleBot(CLIENT_BOT_TOKEN)
        self.mikrotik = MikrotikManager()
        self.pending_requests = {}  # Almacenar solicitudes pendientes
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
            markup.add(
                types.KeyboardButton("📋 Solicitudes"),
                types.KeyboardButton("👥 Usuarios Activos")
            )
            markup.add(types.KeyboardButton("🎫 Generar Ticket"))
        else:
            markup.add(
                types.KeyboardButton("🎫 Solicitar Ticket"),
                types.KeyboardButton("ℹ️ Información")
            )
        return markup
    
    def send_message_safe(self, chat_id, text, reply_to_message_id=None, **kwargs):
        """Envía un mensaje de forma segura, manejando errores comunes"""
        try:
            if reply_to_message_id:
                return self.bot.send_message(chat_id, text, reply_to_message_id=reply_to_message_id, **kwargs)
            else:
                return self.bot.send_message(chat_id, text, **kwargs)
        except Exception as e:
            logger.error(f"Error enviando mensaje: {str(e)}")
            try:
                # Intentar enviar sin reply_to_message_id si falla
                return self.bot.send_message(chat_id, text, **kwargs)
            except Exception as e:
                logger.error(f"Error crítico enviando mensaje: {str(e)}")
                return None

    def reply_safe(self, message, text, **kwargs):
        """Responde a un mensaje de forma segura"""
        try:
            return self.bot.reply_to(message, text, **kwargs)
        except Exception as e:
            logger.error(f"Error respondiendo mensaje: {str(e)}")
            try:
                # Si falla el reply, intentar enviar un mensaje normal
                return self.send_message_safe(message.chat.id, text, **kwargs)
            except Exception as e:
                logger.error(f"Error crítico respondiendo mensaje: {str(e)}")
                return None

    def forward_message_safe(self, chat_id, from_chat_id, message_id):
        """Reenvía un mensaje de forma segura"""
        try:
            return self.bot.forward_message(chat_id, from_chat_id, message_id)
        except Exception as e:
            logger.error(f"Error reenviando mensaje: {str(e)}")
            return None

    def setup_handlers(self):
        """Configura los handlers del bot"""
        # Comando start
        @self.bot.message_handler(commands=['start'])
        def send_welcome(message):
            try:
                user_id = message.from_user.id
                logger.info(f"Usuario iniciando bot - Chat ID: {message.chat.id} User ID: {user_id} Username: @{message.from_user.username}")
                
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
                logger.error(f"Error en send_welcome: {str(e)}")
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
                logger.error(f"Error en request_ticket: {str(e)}")
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
                        logger.info(f"Agregando botón para eliminar usuario: {user['user']}")
                        markup.add(types.InlineKeyboardButton(
                            text=button_text,
                            callback_data=callback_data
                        ))
                        buttons_added = True
                
                if not buttons_added:
                    logger.info("No se agregaron botones al markup")
                
                # Enviar mensaje con botones
                try:
                    self.send_message_safe(
                        message.chat.id,
                        text,
                        reply_markup=markup if buttons_added else None,
                        parse_mode='HTML'
                    )
                    logger.info("Mensaje enviado con éxito")
                except Exception as e:
                    logger.error(f"Error al enviar mensaje: {str(e)}")
                    raise
                
                logger.info(f"Lista de usuarios activos mostrada a {message.from_user.username}")
                
            except Exception as e:
                logger.error(f"Error mostrando usuarios activos: {str(e)}")
                self.reply_safe(message, "❌ Error al obtener usuarios activos")
        
        # Ver solicitudes pendientes
        @self.bot.message_handler(func=lambda message: message.text == "📋 Solicitudes" and self.is_admin(message.from_user.id))
        def show_pending_requests(message):
            try:
                # Mostrar solicitudes pendientes
                if not self.pending_requests:
                    self.reply_safe(
                        message, 
                        "📝 No hay solicitudes pendientes",
                        reply_markup=self.get_user_markup(True)
                    )
                    return
                
                # Enviar cada solicitud con sus botones
                for user_id, request in self.pending_requests.items():
                    try:
                        # Crear botones de acción
                        markup = types.InlineKeyboardMarkup()
                        markup.row(
                            types.InlineKeyboardButton(
                                "✅ Aprobar",
                                callback_data=f"approve_{user_id}"
                            ),
                            types.InlineKeyboardButton(
                                "❌ Rechazar",
                                callback_data=f"reject_{user_id}"
                            )
                        )
                        
                        # Enviar foto y detalles
                        self.bot.send_photo(
                            message.chat.id,
                            request['photo'],
                            caption=f"📝 Solicitud de: @{request['username']}\n"
                                  f"🆔 Chat ID: {user_id}\n"
                                  f"📅 Fecha: {datetime.fromtimestamp(request['date']).strftime('%Y-%m-%d %H:%M:%S')}",
                            reply_markup=markup
                        )
                    except Exception as e:
                        logger.error(f"Error mostrando solicitud {user_id}: {str(e)}")
                        continue
                
            except Exception as e:
                logger.error(f"Error mostrando solicitudes: {str(e)}")
                self.reply_safe(
                    message, 
                    "❌ Error al obtener solicitudes",
                    reply_markup=self.get_user_markup(True)
                )

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
                logger.error(f"Error en admin_generate_ticket: {str(e)}")
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
                logger.error(f"Error en handle_plan_selection: {str(e)}")
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
                        logger.error(f"Error al notificar admin {admin_id}: {str(e)}")
                
                # Confirmar al usuario
                self.reply_safe(
                    message,
                    "✅ Comprobante recibido.\n"
                    "Por favor, espera mientras verificamos tu pago.",
                    reply_markup=self.get_user_markup(self.is_admin(message.from_user.id))
                )
            except Exception as e:
                logger.error(f"Error en handle_payment_proof: {str(e)}")
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
                user_id = int(call.data.split('_')[1])
                
                if action == 'approve':
                    # Generar ticket
                    ticket = self.generate_ticket()
                    
                    # Obtener el mensaje original con la información del plan
                    duration = "1h"  # Plan por defecto
                    
                    # Crear usuario en MikroTik
                    if self.mikrotik.create_user(ticket, ticket, duration):
                        try:
                            # Registrar en el manager
                            manager_logger.info(
                                f"Ticket aprobado - Usuario: @{self.pending_requests[user_id]['username']} "
                                f"(ID: {user_id}) - Ticket: {ticket} - Admin: @{call.from_user.username or 'Unknown'}"
                            )

                            # Enviar ticket al usuario
                            self.send_message_safe(
                                user_id,
                                f"✅ *Tu ticket ha sido generado*\n\n"
                                f"🎫 Ticket: `{ticket}`\n"
                                f"⏱ Tiempo: {duration}\n\n"
                                f"¡Gracias por tu compra! 🙂",
                                parse_mode='Markdown',
                                reply_markup=self.get_user_markup(False)
                            )
                            
                            # Notificar al admin que aprobó
                            self.bot.edit_message_caption(
                                caption=f"✅ Ticket `{ticket}` generado y enviado al usuario.",
                                chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                parse_mode='Markdown'
                            )
                            
                            # Eliminar de solicitudes pendientes
                            if user_id in self.pending_requests:
                                del self.pending_requests[user_id]
                            
                        except Exception as e:
                            logger.error(f"Error al enviar ticket al usuario: {str(e)}")
                            self.bot.answer_callback_query(
                                call.id,
                                "❌ Error al enviar ticket"
                            )
                    else:
                        self.bot.answer_callback_query(
                            call.id,
                            "❌ Error al crear usuario en MikroTik"
                        )
                
                else:  # reject
                    try:
                        # Registrar en el manager
                        manager_logger.info(
                            f"Ticket rechazado - Usuario: @{self.pending_requests[user_id]['username']} "
                            f"(ID: {user_id}) - Admin: @{call.from_user.username or 'Unknown'}"
                        )

                        # Notificar al usuario
                        self.send_message_safe(
                            user_id,
                            "❌ Tu solicitud ha sido rechazada.\n"
                            "Por favor, contacta al administrador para más información.",
                            reply_markup=self.get_user_markup(False)
                        )
                        
                        # Actualizar mensaje del admin
                        self.bot.edit_message_caption(
                            caption="❌ Solicitud rechazada",
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id
                        )
                        
                        # Eliminar de solicitudes pendientes
                        if user_id in self.pending_requests:
                            del self.pending_requests[user_id]
                        
                    except Exception as e:
                        logger.error(f"Error al rechazar solicitud: {str(e)}")
                        self.bot.answer_callback_query(
                            call.id,
                            "❌ Error al rechazar solicitud"
                        )
                
            except Exception as e:
                logger.error(f"Error en handle_ticket_action: {str(e)}")
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
                logger.error(f"Error en handle_admin_ticket_generation: {str(e)}")
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
                logger.info(f"Intentando eliminar usuario: {username}")
                
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
                    logger.info(f"Usuario {username} eliminado por {call.from_user.username}")
                else:
                    self.bot.answer_callback_query(
                        call.id,
                        f"❌ No se pudo eliminar el usuario {username}"
                    )
                    logger.error(f"Error al eliminar usuario {username}")
            
            except Exception as e:
                logger.error(f"Error manejando eliminación de usuario: {str(e)}")
                self.bot.answer_callback_query(
                    call.id,
                    "❌ Error al procesar la solicitud"
                )
    
    def run(self):
        """Inicia el bot"""
        logger.info("Iniciando bot...")
        while True:
            try:
                self.bot.polling(none_stop=True, interval=0)
            except Exception as e:
                logger.error(f"Error en polling: {str(e)}")
                time.sleep(10)  # Esperar antes de reintentar

if __name__ == "__main__":
    try:
        # Limpiar logs al inicio
        open('client_bot.log', 'w').close()  # Limpiar log del bot
        open('manager.log', 'w').close()     # Limpiar log del manager
        
        logger.info("Iniciando bot...")
        bot = SatelWifiBot()
        bot.run()
    except Exception as e:
        logger.error(f"Error principal: {str(e)}")
