import json
import boto3
import logging
from modules.whatsapp import process_verification_webhook
from modules.auction import proccess_auction
from modules.signup import proccess_signup
from modules.whatsapp import send_whatsapp_message
from datetime import datetime
import pytz
import os

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
user_table = dynamodb.Table('cc-prod-bot-user')
message_table = dynamodb.Table('cc-prod-bot-messages')

# Set timezone (adjust to your local timezone)
timezone = pytz.timezone('America/Bogota')
FINAL_HOUR = datetime.fromisoformat(os.environ.get("FINAL_HOUR")).astimezone(timezone)

def process_whatsapp_webhook(event):
    # Verify if user is signup with all fields or if he need to continue signup
    try:
        # Analiza el cuerpo del evento
        body = json.loads(event.get('body', '{}'))
        
        # Extrae datos de WhatsApp
        # Esta estructura dependerá de tu proveedor de API de WhatsApp Business
        # Ajusta según el formato de webhook de tu proveedor
        
        if 'object' in body and body['object'] == 'whatsapp_business_account':
            for entry in body.get('entry', []):
                for change in entry.get('changes', []):
                    if change.get('field') == 'messages':
                        value = change.get('value', {})
                        
                        # Procesa mensaje entrante
                        if 'messages' in value:
                            for message in value.get('messages', []):
                                phone_number = message.get('from', '')
                                logger.info(f"Message from: {phone_number}")

                                # Get current time with timezone
                                now = datetime.now(timezone)

                                if now > FINAL_HOUR:
                                    logger.info(f"Final hour reached: {FINAL_HOUR}. Now is {now}.")
                                    send_whatsapp_message(
                                        phone_number=message.get('from'),
                                        message="La subasta ha concluido. Agradecemos su interés."
                                    )
                                    continue
                                
                                user = user_table.get_item(
                                    Key={'phone': phone_number}
                                )
                                item = user.get('Item')
                                logger.info(f"User info: {item}")
                                if item and item.get("verified"):
                                    logger.info(f"User is already verified: {phone_number}")
                                    # Update last message timestamp
                                    user_table.update_item(
                                        Key={'phone': phone_number},
                                        UpdateExpression='SET last_message = :val1',
                                        ExpressionAttributeValues={
                                            ':val1': message.get('timestamp')
                                        }
                                    )
                                    proccess_auction(message, item)
                                else:
                                    logger.info(f"User in signup process: {phone_number}")
                                    proccess_signup(message, item)

                        
                        # Procesa confirmaciones de entrega o lectura si es necesario
                        if 'statuses' in value:
                            for status in value.get('statuses', []):
                                # Aquí puedes manejar estados de mensajes
                                # Por ejemplo, registrar si se entregó o leyó
                                logger.info(f"Message status: {status.get('id')} - {status.get('status')}")
        
        # Devuelve una respuesta exitosa al webhook
        return {
            'statusCode': 200,
            'body': json.dumps({'status': 'success'})
        }
    
    except Exception as e:
        logger.error(f"Error al procesar webhook: {str(e)}")
        # Devuelve un error HTTP 500 en caso de excepción
        return {
            'statusCode': 500,
            'body': json.dumps({'status': 'error', 'message': str(e)})
        }


def lambda_handler(event, context):
    # Registra el evento recibido (para debugging)
    logger.info("Event received: %s", json.dumps(event))
    
    # Extrae el método HTTP de la estructura correcta del evento
    if 'requestContext' in event and 'http' in event['requestContext']:
        http_method = event['requestContext']['http']['method']
    else:
        http_method = event.get('httpMethod', '')  # Fallback para compatibilidad
    
    if http_method == 'POST':
        # Procesa webhook de WhatsApp
        return process_whatsapp_webhook(event)
    elif http_method == 'GET':
        return process_verification_webhook(event)
    else:
        # Método no permitido
        return {
            'statusCode': 405,
            'body': json.dumps({'status': 'error', 'message': 'Method not allowed'})
        }