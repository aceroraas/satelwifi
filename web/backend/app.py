from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_cors import CORS
import os
import sys
import json
from datetime import datetime
import telebot
from dotenv import load_dotenv
from functools import wraps
import base64
import requests
from io import BytesIO
import random
import string
import logging
import re
from telebot import types
from pathlib import Path
from logger_manager import get_logger
from flask import send_from_directory
import uuid

# Inicializar el logger
logger = get_logger('web_backend')

# Añadir el directorio raíz al path para importar los módulos existentes
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(root_dir)

# Importar el bot y sus configuraciones
import config
from client_bot import SatelWifiBot
from database_manager import DatabaseManager

# Inicializar el bot y la base de datos
bot = SatelWifiBot()
db = DatabaseManager()

app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default-secret-key')

# Configuración de producción
app.config['ENV'] = 'production'
app.config['DEBUG'] = False
app.config['TESTING'] = False
app.config['PROPAGATE_EXCEPTIONS'] = True

# Deshabilitar los logs de Werkzeug excepto errores
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.ERROR)

# Configurar el logger de Flask para usar nuestro sistema centralizado
app.logger.handlers = []
for handler in logger.handlers:
    app.logger.addHandler(handler)
app.logger.setLevel(logger.level)

# Configuración de la carpeta de uploads
UPLOAD_FOLDER = Path(__file__).parent / 'static' / 'uploads' / 'payment_proofs'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Crear la carpeta de uploads si no existe
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_payment_proof(base64_string):
    """Guarda una imagen de comprobante de pago y retorna la ruta"""
    try:
        # Validar que el string base64 no esté vacío
        if not base64_string:
            logger.error('Base64 string está vacío')
            return None
            
        if ',' in base64_string:
            base64_string = base64_string.split(',')[1]
        
        # Validar que el string base64 sea válido
        try:
            image_data = base64.b64decode(base64_string)
        except Exception as e:
            logger.error(f'Error decodificando base64: {str(e)}')
            return None
            
        # Validar que los datos decodificados sean una imagen válida
        if len(image_data) < 100:  # Tamaño mínimo para una imagen válida
            logger.error(f'Datos de imagen muy pequeños: {len(image_data)} bytes')
            return None
        
        # Generar nombre único para el archivo
        filename = f"{uuid.uuid4()}.jpg"
        file_path = UPLOAD_FOLDER / filename
        
        # Guardar archivo
        try:
            with open(file_path, 'wb') as f:
                f.write(image_data)
            logger.info(f'Comprobante guardado exitosamente: {file_path}')
        except Exception as e:
            logger.error(f'Error escribiendo archivo: {str(e)}')
            return None
        
        return str(file_path.relative_to(Path(__file__).parent))
    except Exception as e:
        logger.error(f'Error guardando imagen: {str(e)}')
        return None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def process_base64_image(base64_string):
    """Procesa una imagen en base64"""
    try:
        # Eliminar el prefijo de datos si existe
        if ',' in base64_string:
            base64_string = base64_string.split(',')[1]
        return base64_string.encode('utf-8')
    except Exception as e:
        logger.error(f'Error procesando imagen base64: {str(e)}')
        return None

def generate_ticket():
    """Genera un nuevo ticket"""
    try:
        return bot.generate_ticket()
    except Exception as e:
        logger.error(f'Error generando ticket: {str(e)}')
        return None

def load_pending_requests():
    """Carga las solicitudes pendientes desde la base de datos"""
    return db.get_pending_requests()

def save_pending_requests(requests):
    """Guarda las solicitudes pendientes en la base de datos"""
    return db.save_pending_requests(requests)

# Diccionario global para almacenar solicitudes pendientes
pending_requests = load_pending_requests()

# Función para obtener las solicitudes pendientes
def get_pending_requests():
    """Retorna el diccionario de solicitudes pendientes"""
    return load_pending_requests()

# Función para actualizar una solicitud
def update_request(request_id, status, ticket=None):
    """Actualiza el estado de una solicitud"""
    return db.update_request(request_id, status, ticket)

# Función para obtener las solicitudes pendientes
def get_admin_requests():
    """Obtiene todas las solicitudes pendientes"""
    try:
        requests = db.get_pending_requests()
        requests_dict = {}
        for request in requests:
            # Asegurarse de que todos los campos existan y convertir bytes a base64 si es necesario
            payment_proof = request.get('payment_proof', '')
            if isinstance(payment_proof, bytes):
                payment_proof = base64.b64encode(payment_proof).decode('utf-8')

            request_data = {
                'id': request.get('id', ''),
                'username': request.get('username', ''),
                'plan_data': request.get('plan_data', {}),
                'payment_ref': request.get('payment_ref', ''),
                'payment_proof': payment_proof,
                'status': request.get('status', 'pending'),
                'created_at': request.get('created_at', ''),
                'source': request.get('source', 'web'),
                'chat_id': request.get('chat_id')
            }
            requests_dict[request_data['id']] = request_data
        return jsonify(requests_dict)
    except Exception as e:
        logger.error(f'Error al obtener solicitudes: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == config.ADMIN_USERNAME and password == config.ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin_panel'))
        else:
            return render_template('login.html', error='Credenciales inválidas')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    """Renderiza la página principal"""
    return render_template('index.html', config=config)

@app.route('/api/plans')
def get_plans():
    """Obtiene los planes disponibles"""
    try:
        plans = []
        print("Time plans:", config.time_plans)  # Debug
        print("Prices:", config.PRICES)  # Debug
        for hours in config.time_plans:
            minutes = hours * 60
            plan_key = f"{hours}h" if hours >= 1 else f"{int(minutes)}m"
            prices = config.PRICES[plan_key]
            
            plan = {
                'id': plan_key,
                'name': f"Plan {hours} {'hora' if hours == 1 else 'horas'}",
                'duration': minutes,
                'price_usd': prices['usd'],
                'price_bs': prices['bs']
            }
            print("Adding plan:", plan)  # Debug
            plans.append(plan)
        
        print("Final plans:", plans)  # Debug
        return jsonify(plans)
    except Exception as e:
        print("Error in get_plans:", str(e))  # Debug
        logger.error(f'Error obteniendo planes: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/prices')
def get_prices():
    """Obtiene los precios de los planes"""
    try:
        prices = config.PRICES
        
        return jsonify(prices)
    except Exception as e:
        logger.error(f'Error obteniendo precios: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/submit-request', methods=['POST'])
def submit_request():
    """Envía una nueva solicitud de ticket"""
    try:
        data = request.get_json()
        
        # Validar datos requeridos
        if not all(k in data for k in ['plan', 'paymentRef', 'paymentProof']):
            return jsonify({'error': 'Faltan datos requeridos'}), 400
        
        # Generar ID único para la solicitud
        request_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        # Procesar y guardar imagen del comprobante
        payment_proof_path = None
        if data['paymentProof']:
            payment_proof_path = save_payment_proof(data['paymentProof'])
            if not payment_proof_path:
                return jsonify({'error': 'Error al guardar el comprobante'}), 500
        
        # Guardar la solicitud en la base de datos
        success = db.add_request(
            request_id=request_id,
            plan_data=data['plan'],
            payment_ref=data['paymentRef'],
            payment_proof=payment_proof_path,
            source='web'
        )
        
        if not success:
            # Si falla la base de datos, eliminar la imagen si se guardó
            if payment_proof_path:
                try:
                    os.remove(Path(__file__).parent / payment_proof_path)
                except:
                    pass
            return jsonify({'error': 'Error al guardar la solicitud'}), 500
        
        # Notificar a los administradores
        message = f"""🆕 Nueva Solicitud Web
🔑 ID: {request_id}
📦 Plan: {data['plan']['name']}
💵 Monto: ${data['plan']['price_usd']} / {data['plan']['price_bs']} Bs
🧾 Ref. Pago: {data['paymentRef']}"""
        
        # Crear botones inline
        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = [
            types.InlineKeyboardButton("✅ Aprobar", callback_data=f"web_approve_{request_id}"),
            types.InlineKeyboardButton("❌ Rechazar", callback_data=f"web_reject_{request_id}")
        ]
        markup.add(*buttons)
        
        for admin_id in config.ADMIN_IDS:
            try:
                # Enviar mensaje con la información y botones
                bot.bot.send_message(
                    admin_id, 
                    message,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
                
                # Enviar comprobante si existe
                if payment_proof_path:
                    try:
                        with open(Path(__file__).parent / payment_proof_path, 'rb') as photo:
                            bot.bot.send_photo(admin_id, photo)
                    except Exception as e:
                        logger.error(f'Error enviando comprobante a admin {admin_id}: {str(e)}')
                        bot.bot.send_message(admin_id, "❌ Error al enviar el comprobante de pago")
            except Exception as e:
                logger.error(f'Error enviando notificación a admin {admin_id}: {str(e)}')
        
        return jsonify({'requestId': request_id})
    except Exception as e:
        logger.error(f'Error procesando solicitud: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/check-status/<request_id>')
def check_status(request_id):
    """Verifica el estado de una solicitud"""
    try:
        request_data = db.get_request(request_id)
        if not request_data:
            return jsonify({'error': 'Solicitud no encontrada'}), 404
            
        return jsonify({
            'status': request_data['status'],
            'ticket': request_data.get('ticket', '')
        })
    except Exception as e:
        logger.error(f'Error verificando estado: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/requests', methods=['GET'])
@login_required
def get_admin_requests():
    """Obtiene todas las solicitudes pendientes"""
    try:
        requests = db.get_pending_requests()
        requests_dict = {}
        for request in requests:
            # Asegurarse de que todos los campos existan y convertir bytes a base64 si es necesario
            payment_proof = request.get('payment_proof', '')
            if isinstance(payment_proof, bytes):
                payment_proof = base64.b64encode(payment_proof).decode('utf-8')

            request_data = {
                'id': request.get('id', ''),
                'username': request.get('username', ''),
                'plan_data': request.get('plan_data', {}),
                'payment_ref': request.get('payment_ref', ''),
                'payment_proof': payment_proof,
                'status': request.get('status', 'pending'),
                'created_at': request.get('created_at', ''),
                'source': request.get('source', 'web'),
                'chat_id': request.get('chat_id')
            }
            requests_dict[request_data['id']] = request_data
        return jsonify(requests_dict)
    except Exception as e:
        logger.error(f'Error al obtener solicitudes: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/requests/<request_id>/approve', methods=['POST'])
@login_required
def approve_request(request_id):
    """Aprueba una solicitud"""
    try:
        # Obtener la solicitud
        request_data = db.get_request(request_id)
        if not request_data:
            return jsonify({'error': 'Solicitud no encontrada'}), 404
        
        if request_data['status'] != 'pending':
            return jsonify({'error': 'La solicitud ya fue procesada'}), 400
        
        # Generar ticket
        ticket = generate_ticket()
        if not ticket:
            return jsonify({'error': 'Error generando ticket'}), 500
        
        # Crear usuario en MikroTik
        duration_minutes = request_data['plan_data']['duration']
        duration_hours = duration_minutes / 60
        duration = f"{duration_hours}h"
        if not bot.mikrotik.create_user(ticket, ticket, duration, 'Web', 'Web'):
            return jsonify({'error': 'Error creando usuario en MikroTik'}), 500
        
        # Actualizar estado en la base de datos
        if not db.update_request_status(request_id, 'approved', ticket):
            return jsonify({'error': 'Error actualizando estado de solicitud'}), 500
        
        # Eliminar el comprobante de pago si existe
        if request_data.get('payment_proof'):
            try:
                proof_path = Path(__file__).parent / request_data['payment_proof']
                if proof_path.exists():
                    os.remove(proof_path)
            except Exception as e:
                logger.error(f'Error eliminando comprobante de pago: {str(e)}')
        
        # Notificar al usuario si la solicitud vino del bot
        if request_data.get('chat_id'):
            try:
                bot.send_message_safe(
                    request_data['chat_id'],
                    f" Tu solicitud ha sido aprobada.\n"
                    f" Tu ticket es: <code>{ticket}</code>",
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f'Error notificando al usuario: {str(e)}')
        
        return jsonify({
            'success': True,
            'ticket': ticket
        })
        
    except Exception as e:
        logger.error(f'Error al aprobar solicitud: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/requests/<request_id>/reject', methods=['POST'])
@login_required
def reject_request(request_id):
    """Rechaza una solicitud"""
    try:
        # Obtener la solicitud
        request_data = db.get_request(request_id)
        if not request_data:
            return jsonify({'error': 'Solicitud no encontrada'}), 404
        
        if request_data['status'] != 'pending':
            return jsonify({'error': 'La solicitud ya fue procesada'}), 400
        
        # Actualizar estado en la base de datos
        if not db.update_request_status(request_id, 'rejected'):
            return jsonify({'error': 'Error actualizando estado de solicitud'}), 500
        
        # Eliminar el comprobante de pago si existe
        if request_data.get('payment_proof'):
            try:
                proof_path = Path(__file__).parent / request_data['payment_proof']
                if proof_path.exists():
                    os.remove(proof_path)
            except Exception as e:
                logger.error(f'Error eliminando comprobante de pago: {str(e)}')
        
        # Notificar al usuario si la solicitud vino del bot
        if request_data.get('chat_id'):
            try:
                bot.send_message_safe(
                    request_data['chat_id'],
                    " Lo sentimos, tu solicitud ha sido rechazada.\n"
                    " Por favor, contacta al administrador para más información."
                )
            except Exception as e:
                logger.error(f'Error notificando al usuario: {str(e)}')
        
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f'Error al rechazar solicitud: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/system-status')
@login_required
def system_status():
    """Obtiene el estado del sistema"""
    try:
        # Obtener los últimos logs
        logs = db.get_logs(limit=50)
        
        return jsonify({
            'status': 'ok',
            'logs': logs
        })
    except Exception as e:
        logger.error(f'Error al obtener estado del sistema: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/clear-logs', methods=['POST'])
@login_required
def clear_logs():
    """Limpia los logs del sistema"""
    try:
        # Limpiar archivo de log
        log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'satelwifi.log')
        if os.path.exists(log_path):
            with open(log_path, 'w') as f:
                f.write('')  # Vaciar el archivo
            logger.info("Logs limpiados correctamente")
            return jsonify({'message': 'Logs limpiados correctamente'})
        else:
            return jsonify({'message': 'No hay archivo de logs para limpiar'})
    except Exception as e:
        logger.error(f"Error limpiando logs: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin')
@app.route('/admin/')
@login_required
def admin_panel():
    return render_template('admin.html', config=config)

@app.route('/api/admin/users', methods=['GET'])
@login_required
def get_active_users():
    """Obtiene la lista de usuarios activos"""
    try:
        # Obtener usuarios del router MikroTik
        users = bot.mikrotik.get_active_users()
        if users is None:
            users = []
        
        # Formatear la información de los usuarios
        formatted_users = []
        for user in users:
            if user.get('username', '') == 'default-trial':
                continue
            # Obtener tiempos del usuario
            ticket_time = user.get('uptime', '0s')  # Tiempo total del ticket
            consumed_time = user.get('total_time_consumed', '0s')  # Tiempo consumido
            remaining_time = user.get('time_left', '0s')  # Tiempo restante
            
            # Formatear tiempo total del ticket
            if not ticket_time or ticket_time == '0s':
                formatted_total = 'Sin límite'
            else:
                try:
                    formatted_total = ticket_time  # Ya viene formateado del MikrotikManager
                except:
                    formatted_total = 'Error en formato'
            
            # Formatear tiempo consumido
            if not consumed_time or consumed_time == '0s':
                formatted_uptime = 'Sin actividad'
            else:
                try:
                    formatted_uptime = consumed_time  # Ya viene formateado del MikrotikManager
                except:
                    formatted_uptime = 'Error en formato'
            
            
            formatted_user = {
                'username': user.get('user', 'Sin nombre'),
                'telegramUser': user.get('telegram', 'Unknown'),
                'isActive': user.get('is_active', False),
                'uptime': formatted_uptime,
                'totalTime': formatted_total,
                'timeLeft': remaining_time,
                'ipAddress': user.get('address', 'Sin IP'),
                'status': 'active' if user.get('is_active', False) else 'inactive',
                'createdBy': user.get('created_by', 'Unknown'),
                'createdAt': user.get('created_at', 'Unknown')
            }
            formatted_users.append(formatted_user)
        
        # Ordenar usuarios: primero los activos, luego por nombre
        formatted_users.sort(key=lambda x: (-x['isActive'], x['username']))
        
        return jsonify(formatted_users)
    except Exception as e:
        logger.error(f'Error obteniendo usuarios activos: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/users/<username>', methods=['DELETE'])
@login_required
def delete_user(username):
    """Elimina un usuario del sistema"""
    try:
        # Intentar eliminar el usuario del router
        if bot.mikrotik.remove_user(username):
            # Si se eliminó correctamente, eliminar de la base de datos
            db.remove_user(username)
            logger.info(f'Usuario {username} eliminado correctamente')
            return jsonify({'status': 'success'})
        else:
            logger.error(f'Error al eliminar usuario {username} del router')
            return jsonify({'error': 'Error al eliminar usuario del router'}), 500
    except Exception as e:
        logger.error(f'Error al eliminar usuario {username}: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/refund', methods=['POST'])
def submit_refund():
    """Envía los datos de devolución a los administradores por Telegram"""
    try:
        data = request.get_json()
        
        # Validar datos requeridos
        required_fields = ['username', 'reason', 'amount']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'error': f'Falta el campo requerido: {field}'
                }), 400
        
        # Construir mensaje
        message_parts = [
            " Solicitud de Devolución",
            f" Usuario: {data['username']}",
            f" Monto: ${data['amount']}",
            f" Motivo: {data['reason']}"
        ]
        
        # Añadir campos opcionales si están presentes
        if 'ticket' in data:
            message_parts.append(f" Ticket: {data['ticket']}")
        if 'comments' in data:
            message_parts.append(f" Comentarios: {data['comments']}")
        
        # Unir todas las partes del mensaje
        message = "\n".join(message_parts)
        
        # Enviar mensaje a todos los administradores
        for admin_id in config.ADMIN_IDS:
            try:
                bot.bot.send_message(admin_id, message)
            except Exception as e:
                logger.error(f'Error enviando mensaje a admin {admin_id}: {str(e)}')
        
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f'Error al procesar solicitud de devolución: {str(e)}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/system-logs')
@login_required
def system_logs():
    """Obtiene los logs del sistema del archivo centralizado"""
    try:
        log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'satelwifi.log')
        logs = []
        
        if os.path.exists(log_path):
            with open(log_path, 'r') as f:
                for line in f.readlines()[-1000:]:  # Obtener las últimas 1000 líneas
                    try:
                        # Parsear la línea de log
                        # Formato: timestamp - name - level - message
                        parts = line.strip().split(' - ', 3)
                        if len(parts) >= 4:
                            timestamp, name, level, message = parts
                            logs.append({
                                'timestamp': timestamp,
                                'source': name,
                                'level': level,
                                'message': message
                            })
                    except Exception as e:
                        logger.error(f"Error parsing log line: {str(e)}")
                        continue
        
        return jsonify({
            'logs': logs
        })
    except Exception as e:
        logger.error(f"Error reading system logs: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/image/<path:filename>')
@login_required
def serve_image(filename):
    """Sirve las imágenes de los comprobantes"""
    try:
        return send_from_directory(UPLOAD_FOLDER, filename)
    except Exception as e:
        logger.error(f'Error sirviendo imagen {filename}: {str(e)}')
        return 'Imagen no encontrada', 404

if __name__ == '__main__':
    app.run(debug=False, port=5000)
