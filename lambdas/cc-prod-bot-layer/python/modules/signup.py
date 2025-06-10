import boto3
import logging
from modules.whatsapp import send_whatsapp_message, get_media_content
import os
import time
from io import BytesIO
from datetime import datetime
import pytz

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

PROPERTY_ADDRESS = os.environ.get("PROPERTY_ADDRESS")
TERMS_AND_CONDITIONS = os.environ.get("TERMS_AND_CONDITIONS")

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
user_table = dynamodb.Table('cc-prod-bot-user')
s3 = boto3.client('s3')

# Set timezone (adjust to your local timezone)
timezone = pytz.timezone('America/Bogota')
SIGNUP_INITIAL_HOUR = datetime.fromisoformat(os.environ.get("SIGNUP_INITIAL_HOUR")).astimezone(timezone)
SIGNUP_FINAL_HOUR = datetime.fromisoformat(os.environ.get("SIGNUP_FINAL_HOUR")).astimezone(timezone)

def proccess_signup(message, user):
    now = datetime.now(timezone)
    if now < SIGNUP_INITIAL_HOUR:
        logger.info("Auction has not started yet.")
        send_whatsapp_message(
            phone_number=message.get('from'),
            message=f"El periodo para registrarse en la subasta aún no ha comenzado. Estará disponible a partir del {SIGNUP_INITIAL_HOUR.strftime('%Y-%m-%d a las %H:%M')}."
        )
        return
    elif now > SIGNUP_FINAL_HOUR:
        logger.info("Auction has already ended.")
        send_whatsapp_message(
            phone_number=message.get('from'),
            message="El proceso de registro para participar en la subasta ha terminado. Agradecemos su interés."
        )
        return
    if not user:
        # Create a new user in DynamoDB
        user_table.put_item(
            Item={
                'phone': message.get('from'),
                'terms_document': [],
                'status': 'pending_terms',
                'created_at': message.get('timestamp'),
                'last_message': message.get('timestamp')
            }
        )
        logger.info(f"New user created: {message.get('from')}")
        # Mensaje de bienvenida
        send_whatsapp_message(
            phone_number=message.get('from'),
            message=f"¡Bienvenido(a) a la subasta del canon de arrendamiento de {PROPERTY_ADDRESS}!"
        )

        # Get S3 presigned url
        bucket_name, key = TERMS_AND_CONDITIONS.replace("s3://", "").split("/", 1)
        file_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': key},
            ExpiresIn=60
        )

        # Esperar 1 segundo antes de enviar el siguiente mensaje
        time.sleep(1)

        # Enviar política de privacidad y términos
        send_whatsapp_message(
            phone_number=message.get('from'),
            message=(
                "Antes de participar en la subasta, es necesario que lea y acepte los términos y condiciones sobre el uso de este bot "
                "y el proceso de subasta. Para ello, debe diligenciar a mano el documento adjunto."
            ),
            file=file_url,
            filename="Formato de Oferta.pdf"
        )

        # Esperar 3 segundos antes de enviar el siguiente mensaje
        time.sleep(3)

        send_whatsapp_message(
            phone_number=message.get('from'),
            message=(
                "Recuerde que debe diligenciar un único documento, incluyendo a todas las personas a cuyo nombre se elaborará el contrato de arrendamiento en caso de resultar ganadores. "
                "Las pujas durante la subasta deberán realizarse exclusivamente desde el número de WhatsApp desde el cual se envió dicho documento."
            )
        )

        time.sleep(3)
        send_whatsapp_message(
            phone_number=message.get('from'),
            message=(
                f"Una vez haya diligenciado el documento, por favor escanee todas sus páginas y adjúntelas en un único archivo PDF en este chat. Recuerde que el plazo máximo para enviar el documento es {SIGNUP_FINAL_HOUR.strftime('%Y-%m-%d a las %H:%M')}."
            )
        )

    else:
        # Check if message has a file
        document = message.get('document')
        if message.get('type') == 'document'  and document and document["mime_type"] == 'application/pdf':
            # get media url
            file_content = get_media_content(document["id"])
            if not file_content:
                send_whatsapp_message(
                    phone_number=message.get('from'),
                    message=(
                        "No se pudo obtener el archivo. Por favor, intente nuevamente."
                    )
                )
                return
        
            # upload file to S3
            bucket_name, key = TERMS_AND_CONDITIONS.replace("s3://", "").split("/", 1)
            s3_key = "terms_documents/" + message.get('from') + "/" + message.get('timestamp') + ".pdf"
            file_data = BytesIO(file_content)
            s3.upload_fileobj(
                file_data,
                bucket_name,
                s3_key,
                ExtraArgs={
                    'ContentType': document["mime_type"],
                    'Metadata': {
                        'phone': message.get('from'),
                        'timestamp': message.get('timestamp')
                    }
                }
            )
            logger.info(f"File uploaded to S3: s3://{bucket_name}/{s3_key}")
            user_table.update_item(
                Key={
                    'phone': message.get('from')
                },
                UpdateExpression="SET terms_document = list_append(if_not_exists(terms_document, :empty_list), :i)",
                ExpressionAttributeValues={
                    ':i': [f"s3://{bucket_name}/{s3_key}"],
                    ':empty_list': []
                }
            )
            send_whatsapp_message(
                phone_number=message.get('from'),
                message="El documento ha sido recibido y se está procesando. Le notificaremos cuando esté listo para participar en la subasta."
            )
        else:
            documents = user.get('terms_document', [])
            if len(documents) == 0:
                send_whatsapp_message(
                    phone_number=message.get('from'),
                    message=(
                        "En este momento solo debe enviar el documento de términos y condiciones como un único archivo PDF. "
                        "No envíe otros mensajes o archivos. "
                    )
                )
            else:
                send_whatsapp_message(
                    phone_number=message.get('from'),
                    message=(
                        "Ya hemos recibido un documento anteriormente. Si necesita enviar una versión corregida, "
                        "por favor adjúntela como un único archivo PDF. Si ya envió la versión correcta, "
                        "le notificaremos próximas acciones una vez hayamos revisado su documentación."
                    )
                )