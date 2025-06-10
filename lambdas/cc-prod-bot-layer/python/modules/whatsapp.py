import json
import os
import logging
import requests

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def process_verification_webhook(event):
    # Para verificación de webhook (requerido por WhatsApp Business API)
    query_params = event.get('queryStringParameters', {}) or {}
    
    # Verificación sin parámetros - caso de navegación web directa
    if not query_params:
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'text/html'
            },
            'body': json.dumps({'status': 'success'})
        }
    
    # Verifica el token de verificación
    verify_token = os.environ.get('WHATSAPP_VERIFY_TOKEN')
    mode = query_params.get('hub.mode')
    token = query_params.get('hub.verify_token')
    challenge = query_params.get('hub.challenge')
    
    if mode == 'subscribe' and token == verify_token:
        return {
            'statusCode': 200,
            'body': challenge
        }
    else:
        return {
            'statusCode': 403,
            'body': json.dumps({'status': 'error', 'message': 'Verification failed'})
        }

def create_button_message(text, buttons):
    """
    Crea un mensaje con botones para WhatsApp Business API
    
    Args:
        text (str): Texto principal del mensaje
        buttons (list): Lista de diccionarios con los botones. Cada botón debe tener keys 'id' y 'text'
    
    Returns:
        dict: Estructura de mensaje con botones para la API de WhatsApp
    """
    button_objects = []
    for button in buttons:
        button_objects.append({
            "type": "reply",
            "reply": {
                "id": button["id"],
                "title": button["text"]
            }
        })
    
    return {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": text
            },
            "action": {
                "buttons": button_objects
            }
        }
    }

def create_file_message(file_url, caption, filename=None):
    """
    Crea un mensaje con archivo para WhatsApp Business API
    
    Args:
        file_url (str): URL del archivo a enviar
        caption (str): Texto de la leyenda del archivo
    
    Returns:
        dict: Estructura de mensaje con archivo para la API de WhatsApp
    """
    return {
        "type": "document",
        "document": {
            "link": file_url,
            "caption": caption,
            "filename": filename
        }
    }

def send_whatsapp_message(phone_number, message, file=None, buttons=None, filename=None):
    """
    Envía un mensaje a través de la API de WhatsApp Business
    
    Args:
        phone_number (str): Número de teléfono del destinatario
        message (str): Mensaje de texto a enviar
        buttons (list, optional): Lista de botones para incluir
    """
    
    # Configuración de la API de WhatsApp Business
    whatsapp_api_url = 'https://graph.facebook.com/v22.0'
    phone_number_id = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
    whatsapp_token = os.environ.get('WHATSAPP_ACCESS_TOKEN')
    
    # URL para enviar mensajes
    url = f"{whatsapp_api_url}/{phone_number_id}/messages"
    
    # Encabezados para la llamada HTTP
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {whatsapp_token}"
    }
    
    # Estructura base del payload
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number,
        "ttl": 300
    }
    
    # Configurar el tipo de mensaje
    if buttons:
        # Mensaje con botones interactivos
        message_data = create_button_message(message, buttons)
        payload["type"] = "interactive"
        payload["interactive"] = message_data["interactive"]
    elif file:
        # Mensaje con archivo
        message_data = create_file_message(file, message, filename)
        payload["type"] = "document"
        payload["document"] = message_data["document"]
    else:
        # Mensaje de texto simple
        payload["type"] = "text"
        payload["text"] = {"body": message}
    
    try:
        # Realizar la llamada HTTP a la API de WhatsApp
        logger.info("Sending whatsapp message: %s", json.dumps(payload))
        response = requests.post(url, headers=headers, json=payload)
        
        # Procesar la respuesta
        if response.status_code == 200:
            logger.info(f"Mensaje enviado exitosamente: {response.text}")
            return True
        else:
            logger.error(f"Error al enviar mensaje. Código: {response.status_code}, Respuesta: {response.text}")
            return False
    
    except Exception as e:
        logger.error(f"Excepción al enviar mensaje de WhatsApp: {str(e)}")
        return False
    
def send_whatsapp_template(phone_number, template_name, template_language, template_params=None):
    """
    Envía un mensaje de plantilla a través de la API de WhatsApp Business
    
    Args:
        phone_number (str): Número de teléfono del destinatario
        template_name (str): Nombre de la plantilla
        template_language (str): Idioma de la plantilla
        template_params (list, optional): Parámetros para la plantilla
    """
    
    # Configuración de la API de WhatsApp Business
    whatsapp_api_url = 'https://graph.facebook.com/v22.0'
    phone_number_id = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
    whatsapp_token = os.environ.get('WHATSAPP_ACCESS_TOKEN')
    
    # URL para enviar mensajes
    url = f"{whatsapp_api_url}/{phone_number_id}/messages"
    
    # Encabezados para la llamada HTTP
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {whatsapp_token}"
    }
    
    # Estructura base del payload
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone_number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {
                "code": template_language
            }
        }
    }
    
    if template_params:
        payload["template"]["components"] = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": param} for param in template_params]
            }
        ]
    
    try:
        # Realizar la llamada HTTP a la API de WhatsApp
        logger.info("Sending whatsapp template: %s", json.dumps(payload))
        response = requests.post(url, headers=headers, json=payload)
        
        # Procesar la respuesta
        if response.status_code == 200:
            logger.info(f"Plantilla enviada exitosamente: {response.text}")
            return True
        else:
            logger.error(f"Error al enviar plantilla. Código: {response.status_code}, Respuesta: {response.text}")
            return False
    
    except Exception as e:
        logger.error(f"Excepción al enviar plantilla de WhatsApp: {str(e)}")
        return False
    
def get_media_url(media_id):
    """
    Gets the URL of a media file from its ID
    
    Args:
        media_id (str): ID of the media file
    
    Returns:
        str: URL of the media file
    """
    whatsapp_api_url = 'https://graph.facebook.com/v22.0'
    whatsapp_token = os.environ.get('WHATSAPP_ACCESS_TOKEN')
    url = f"{whatsapp_api_url}/{media_id}"
    headers = {"Authorization": f"Bearer {whatsapp_token}"}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()['url']
        logger.error(f"Error getting media URL. Code: {response.status_code}, Response: {response.text}")
        return None
    except Exception as e:
        logger.error(f"Exception getting media URL: {str(e)}")
        return None

def get_media_content(media_id):
    """
    Gets the content of a media file from its ID
    
    Args:
        media_id (str): ID of the media file
    
    Returns:
        bytes: Content of the media file
    """
    media_url = get_media_url(media_id)
    if not media_url:
        return None
        
    headers = {"Authorization": f"Bearer {os.environ.get('WHATSAPP_ACCESS_TOKEN')}"}
    try:
        response = requests.get(media_url, headers=headers)
        return response.content if response.status_code == 200 else None
    except Exception as e:
        logger.error(f"Exception downloading media content: {str(e)}")
        return None