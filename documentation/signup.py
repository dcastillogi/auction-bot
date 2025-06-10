import boto3
import logging
from modules.whatsapp import send_whatsapp_message
from modules.auction import proccess_auction
import os

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

PROPERTY_ADDRESS = os.environ.get("PROPERTY_ADDRESS")
TERMS_AND_CONDITIONS = os.environ.get("TERMS_AND_CONDITIONS")

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
user_table = dynamodb.Table('cc-prod-bot-user')

VALID_ID_DOCUMENTS_FOR_RENTAL = {
    "CC": "Cédula de Ciudadanía",
    "CE": "Cédula de Extranjería",
    "PPT": "Permiso por Protección Temporal"
}

def proccess_signup(message, user):
    # If user does not exist
    if not user:
        # Create a new user in DynamoDB
        user_table.put_item(
            Item={
                'phone': message.get('from'),
                'document_type': None,
                'document': None,
                'name': None,
                'email': None,
                'address': None,
                'city': None,
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
        
        # Enviar política de privacidad y términos
        send_whatsapp_message(
            phone_number=message.get('from'),
            message=(
                "Antes de participar en la subasta, es necesario que revise y acepte los términos y condiciones "
                "relacionados con el uso de este bot y el proceso de subasta. Puede consultarlos en el siguiente enlace:\n"
                f"{TERMS_AND_CONDITIONS}"
            ),
            buttons=[
                {"text": "Acepto", "id": "accept_terms"}
            ]
        )
    else:
        if user.get('status') == 'pending_terms':
            flag = False
            if message.get('type') == 'interactive':
                interactive = message.get('interactive', {})
                
                # Maneja diferentes tipos de interacciones
                if interactive.get('type') == 'button_reply':
                    button_reply = interactive.get('button_reply', {})
                    button_id = button_reply.get('id', '')
                    if button_id == 'accept_terms':
                        # User accepted terms and conditions
                        user_table.update_item(
                            Key={'phone': message.get('from')},
                            UpdateExpression="SET #status = :status",
                            ExpressionAttributeNames={
                                '#status': 'status'
                            },
                            ExpressionAttributeValues={
                                ':status': 'accepted_terms'
                            }
                        )
                        user["status"] = "accepted_terms"
                        logger.info(f"User accepted terms: {message.get('from')}")
                        flag = True
                        process_data_signup(message, user)
            if not flag:
                # User has not accepted terms and conditions
                send_whatsapp_message(
                    phone_number=message.get('from'),
                    message=f"Por favor, acepte los términos y condiciones ({TERMS_AND_CONDITIONS}) para continuar.",
                    buttons=[
                        {"text": "Acepto", "id": "accept_terms"}
                    ]
                )
        else:
            # Process data collection
            process_data_signup(message, user)
        
def process_data_signup(message, user):
    """Main handler for signup process flow"""
    status = user.get('status', '')
    
    if status == 'accepted_terms':
        process_document_type(message, user)
    elif status == 'pending_document_type':
        process_document_type(message, user)
    elif status == 'pending_document':
        process_document(message, user)
    elif status == 'pending_document_confirmation':
        confirm_document(message, user)
    elif status == 'pending_name':
        process_name(message, user)
    elif status == 'pending_name_confirmation':
        confirm_name(message, user)
    elif status == 'pending_email':
        process_email(message, user)
    elif status == 'pending_email_confirmation':
        confirm_email(message, user)
    elif status == 'pending_address':
        process_address(message, user)
    elif status == 'pending_address_confirmation':
        confirm_address(message, user)
    elif status == 'pending_city':
        process_city(message, user)
    elif status == 'pending_city_confirmation':
        confirm_city(message, user)
    else:
        proccess_auction(message, user)

def process_document_type(message, user):
    """Handle document type selection"""
    flag = False
    if message.get('type') == 'interactive':
        interactive = message.get('interactive', {})
        if interactive.get('type') == 'button_reply':
            button_reply = interactive.get('button_reply', {})
            button_id = button_reply.get('id', '')
            if button_id in VALID_ID_DOCUMENTS_FOR_RENTAL.keys():
                # Save document type
                user_table.update_item(
                    Key={'phone': message.get('from')},
                    UpdateExpression="SET #status = :status, #doc_type = :doc_type",
                    ExpressionAttributeNames={
                        '#status': 'status',
                        '#doc_type': 'document_type'
                    },
                    ExpressionAttributeValues={
                        ':status': 'pending_document',
                        ':doc_type': button_id
                    }
                )
                user["status"] = "pending_document"
                user["document_type"] = button_id
                logger.info(f"User selected document type: {button_id}")
                flag = True
                request_document(message, user)
    
    if not flag:
        # Botones solo con los códigos
        buttons = [{"id": key, "text": key} for key in VALID_ID_DOCUMENTS_FOR_RENTAL.keys()]
        
        # Descripción completa en el mensaje
        doc_list = "\n".join([f"{key}: {value}" for key, value in VALID_ID_DOCUMENTS_FOR_RENTAL.items()])
        
        # Enviar mensaje
        send_whatsapp_message(
            phone_number=message.get('from'),
            message=f"Para continuar, seleccione el tipo de su documento de identidad:\n\n{doc_list}",
            buttons=buttons
        )

        # Update user status
        user_table.update_item(
            Key={'phone': message.get('from')},
            UpdateExpression="SET #status = :status",
            ExpressionAttributeNames={
                '#status': 'status'
            },
            ExpressionAttributeValues={
                ':status': 'pending_document_type'
            }
        )

def request_document(message, user):
    """Request document number based on selected type"""
    doc_type = user.get('document_type', '')
    doc_name = VALID_ID_DOCUMENTS_FOR_RENTAL.get(doc_type, 'Documento')
    
    send_whatsapp_message(
        phone_number=message.get('from'),
        message=f"Por favor, ingrese su número de {doc_name} sin puntos ni espacios:"
    )

def process_document(message, user):
    """Process and validate document number"""
    if message.get('type') == 'text':
        document = message.get('text', {}).get('body', '').strip()
        
        # Basic document validation based on type
        doc_type = user.get('document_type', '')
        is_valid = validate_document(document, doc_type)
        
        if is_valid:
            # Save document
            user_table.update_item(
                Key={'phone': message.get('from')},
                UpdateExpression="SET #status = :status, #document = :document",
                ExpressionAttributeNames={
                    '#status': 'status',
                    '#document': 'document'
                },
                ExpressionAttributeValues={
                    ':status': 'pending_document_confirmation',
                    ':document': document
                }
            )
            user["status"] = "pending_document_confirmation"
            user["document"] = document
            
            # Request confirmation
            send_whatsapp_message(
                phone_number=message.get('from'),
                message=f"¿Es correcto su número de documento: {document}?",
                buttons=[
                    {"id": "confirm_doc_yes", "text": "Sí, es correcto"},
                    {"id": "confirm_doc_no", "text": "No, corregir"}
                ]
            )
        else:
            # Invalid document format
            doc_type_name = VALID_ID_DOCUMENTS_FOR_RENTAL.get(doc_type, 'documento')
            send_whatsapp_message(
                phone_number=message.get('from'),
                message=f"El formato del {doc_type_name} no parece ser válido. Por favor verifique e intente nuevamente:"
            )
    else:
        # Not a text message, ask again
        request_document(message, user)

def validate_document(document, doc_type):
    """Validate document number based on type"""
    if not document:
        return False
        
    # Basic validation based on document type
    if doc_type == "CC":  # Colombian ID
        # Only numbers, length between 8-10 digits
        return document.isdigit() and 8 <= len(document) <= 10
    elif doc_type == "CE":  # Foreign ID
        return len(document) >= 6 and len(document) <= 12
    elif doc_type == "PAS":  # Passport
        # Alphanumeric, length between 6-12 chars
        return 6 <= len(document) <= 12
    elif doc_type == "PEP":  # Special permit
        return document.isalnum() and len(document) >= 8
    else:
        # Default validation - at least 4 characters
        return len(document) >= 4

def confirm_document(message, user):
    """Handle document confirmation"""
    if message.get('type') == 'interactive':
        interactive = message.get('interactive', {})
        if interactive.get('type') == 'button_reply':
            button_id = interactive.get('button_reply', {}).get('id', '')
            
            if button_id == "confirm_doc_yes":
                # Document confirmed, move to next step (name)
                user_table.update_item(
                    Key={'phone': message.get('from')},
                    UpdateExpression="SET #status = :status",
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': 'pending_name'}
                )
                user["status"] = "pending_name"
                request_name(message, user)
            elif button_id == "confirm_doc_no":
                # Document not confirmed, ask again
                user_table.update_item(
                    Key={'phone': message.get('from')},
                    UpdateExpression="SET #status = :status",
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': 'pending_document'}
                )
                user["status"] = "pending_document"
                request_document(message, user)
    else:
        # Not an interactive message, ask again for confirmation
        document = user.get('document', '')
        send_whatsapp_message(
            phone_number=message.get('from'),
            message=f"¿Es correcto su número de documento: {document}?",
            buttons=[
                {"id": "confirm_doc_yes", "text": "Sí, es correcto"},
                {"id": "confirm_doc_no", "text": "No, corregir"}
            ]
        )

def request_name(message, user):
    """Request user's full name"""
    send_whatsapp_message(
        phone_number=message.get('from'),
        message="Por favor, ingrese su nombre completo:"
    )

def process_name(message, user):
    """Process and validate name"""
    if message.get('type') == 'text':
        name = message.get('text', {}).get('body', '').strip()
        
        # Basic name validation
        if len(name) >= 5 and len(name.split()) >= 2:
            # Name looks valid, save and request confirmation
            user_table.update_item(
                Key={'phone': message.get('from')},
                UpdateExpression="SET #status = :status, #name = :name",
                ExpressionAttributeNames={
                    '#status': 'status',
                    '#name': 'name'
                },
                ExpressionAttributeValues={
                    ':status': 'pending_name_confirmation',
                    ':name': name
                }
            )
            user["status"] = "pending_name_confirmation"
            user["name"] = name
            
            # Request confirmation
            send_whatsapp_message(
                phone_number=message.get('from'),
                message=f"¿Es correcto su nombre: {name}?",
                buttons=[
                    {"id": "confirm_name_yes", "text": "Sí, es correcto"},
                    {"id": "confirm_name_no", "text": "No, corregir"}
                ]
            )
        else:
            # Invalid name format
            send_whatsapp_message(
                phone_number=message.get('from'),
                message="Por favor ingrese su nombre completo (nombre y apellido):"
            )
    else:
        # Not a text message, ask again
        request_name(message, user)

def confirm_name(message, user):
    """Handle name confirmation"""
    if message.get('type') == 'interactive':
        interactive = message.get('interactive', {})
        if interactive.get('type') == 'button_reply':
            button_id = interactive.get('button_reply', {}).get('id', '')
            
            if button_id == "confirm_name_yes":
                # Name confirmed, move to next step (email)
                user_table.update_item(
                    Key={'phone': message.get('from')},
                    UpdateExpression="SET #status = :status",
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': 'pending_email'}
                )
                user["status"] = "pending_email"
                request_email(message, user)
            elif button_id == "confirm_name_no":
                # Name not confirmed, ask again
                user_table.update_item(
                    Key={'phone': message.get('from')},
                    UpdateExpression="SET #status = :status",
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': 'pending_name'}
                )
                user["status"] = "pending_name"
                request_name(message, user)
    else:
        # Not an interactive message, ask again for confirmation
        name = user.get('name', '')
        send_whatsapp_message(
            phone_number=message.get('from'),
            message=f"¿Es correcto su nombre: {name}?",
            buttons=[
                {"id": "confirm_name_yes", "text": "Sí, es correcto"},
                {"id": "confirm_name_no", "text": "No, corregir"}
            ]
        )

def request_email(message, user):
    """Request user's email"""
    send_whatsapp_message(
        phone_number=message.get('from'),
        message="Por favor, ingrese su correo electrónico:"
    )

def process_email(message, user):
    """Process and validate email"""
    if message.get('type') == 'text':
        email = message.get('text', {}).get('body', '').strip()
        
        # Email validation
        if validate_email(email):
            # Email looks valid, save and request confirmation
            user_table.update_item(
                Key={'phone': message.get('from')},
                UpdateExpression="SET #status = :status, #email = :email",
                ExpressionAttributeNames={
                    '#status': 'status',
                    '#email': 'email'
                },
                ExpressionAttributeValues={
                    ':status': 'pending_email_confirmation',
                    ':email': email
                }
            )
            user["status"] = "pending_email_confirmation"
            user["email"] = email
            
            # Request confirmation
            send_whatsapp_message(
                phone_number=message.get('from'),
                message=f"¿Es correcto su correo electrónico: {email}?",
                buttons=[
                    {"id": "confirm_email_yes", "text": "Sí, es correcto"},
                    {"id": "confirm_email_no", "text": "No, corregir"}
                ]
            )
        else:
            # Invalid email format
            send_whatsapp_message(
                phone_number=message.get('from'),
                message="El formato del correo electrónico no es válido. Por favor ingrese un correo electrónico válido:"
            )
    else:
        # Not a text message, ask again
        request_email(message, user)

def validate_email(email):
    """Validate email format"""
    import re
    # Basic email regex pattern
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def confirm_email(message, user):
    """Handle email confirmation"""
    if message.get('type') == 'interactive':
        interactive = message.get('interactive', {})
        if interactive.get('type') == 'button_reply':
            button_id = interactive.get('button_reply', {}).get('id', '')
            
            if button_id == "confirm_email_yes":
                # Email confirmed, move to next step (address)
                user_table.update_item(
                    Key={'phone': message.get('from')},
                    UpdateExpression="SET #status = :status",
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': 'pending_address'}
                )
                user["status"] = "pending_address"
                request_address(message, user)
            elif button_id == "confirm_email_no":
                # Email not confirmed, ask again
                user_table.update_item(
                    Key={'phone': message.get('from')},
                    UpdateExpression="SET #status = :status",
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': 'pending_email'}
                )
                user["status"] = "pending_email"
                request_email(message, user)
    else:
        # Not an interactive message, ask again for confirmation
        email = user.get('email', '')
        send_whatsapp_message(
            phone_number=message.get('from'),
            message=f"¿Es correcto su correo electrónico: {email}?",
            buttons=[
                {"id": "confirm_email_yes", "text": "Sí, es correcto"},
                {"id": "confirm_email_no", "text": "No, corregir"}
            ]
        )

def request_address(message, user):
    """Request user's address"""
    send_whatsapp_message(
        phone_number=message.get('from'),
        message="Por favor, ingrese su dirección completa:"
    )

def process_address(message, user):
    """Process and validate address"""
    if message.get('type') == 'text':
        address = message.get('text', {}).get('body', '').strip()
        
        # Basic address validation
        if len(address) >= 5:
            # Address looks valid, save and request confirmation
            user_table.update_item(
                Key={'phone': message.get('from')},
                UpdateExpression="SET #status = :status, #address = :address",
                ExpressionAttributeNames={
                    '#status': 'status',
                    '#address': 'address'
                },
                ExpressionAttributeValues={
                    ':status': 'pending_address_confirmation',
                    ':address': address
                }
            )
            user["status"] = "pending_address_confirmation"
            user["address"] = address
            
            # Request confirmation
            send_whatsapp_message(
                phone_number=message.get('from'),
                message=f"¿Es correcta su dirección: {address}?",
                buttons=[
                    {"id": "confirm_address_yes", "text": "Sí, es correcta"},
                    {"id": "confirm_address_no", "text": "No, corregir"}
                ]
            )
        else:
            # Invalid address format
            send_whatsapp_message(
                phone_number=message.get('from'),
                message="Por favor ingrese una dirección válida:"
            )
    else:
        # Not a text message, ask again
        request_address(message, user)

def confirm_address(message, user):
    """Handle address confirmation"""
    if message.get('type') == 'interactive':
        interactive = message.get('interactive', {})
        if interactive.get('type') == 'button_reply':
            button_id = interactive.get('button_reply', {}).get('id', '')
            
            if button_id == "confirm_address_yes":
                # Address confirmed, move to next step (city)
                user_table.update_item(
                    Key={'phone': message.get('from')},
                    UpdateExpression="SET #status = :status",
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': 'pending_city'}
                )
                user["status"] = "pending_city"
                request_city(message, user)
            elif button_id == "confirm_address_no":
                # Address not confirmed, ask again
                user_table.update_item(
                    Key={'phone': message.get('from')},
                    UpdateExpression="SET #status = :status",
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': 'pending_address'}
                )
                user["status"] = "pending_address"
                request_address(message, user)
    else:
        # Not an interactive message, ask again for confirmation
        address = user.get('address', '')
        send_whatsapp_message(
            phone_number=message.get('from'),
            message=f"¿Es correcta su dirección: {address}?",
            buttons=[
                {"id": "confirm_address_yes", "text": "Sí, es correcta"},
                {"id": "confirm_address_no", "text": "No, corregir"}
            ]
        )

def request_city(message, user):
    """Request user's city"""
    # You could provide a list of common cities as buttons
    # or just ask for free text input
    send_whatsapp_message(
        phone_number=message.get('from'),
        message="Por favor, ingrese su ciudad de residencia:"
    )

def process_city(message, user):
    """Process and validate city"""
    if message.get('type') == 'text':
        city = message.get('text', {}).get('body', '').strip()
        
        # Basic city validation
        if len(city) >= 3:
            # City looks valid, save and request confirmation
            user_table.update_item(
                Key={'phone': message.get('from')},
                UpdateExpression="SET #status = :status, #city = :city",
                ExpressionAttributeNames={
                    '#status': 'status',
                    '#city': 'city'
                },
                ExpressionAttributeValues={
                    ':status': 'pending_city_confirmation',
                    ':city': city
                }
            )
            user["status"] = "pending_city_confirmation"
            user["city"] = city
            
            # Request confirmation
            send_whatsapp_message(
                phone_number=message.get('from'),
                message=f"¿Es correcta su ciudad: {city}?",
                buttons=[
                    {"id": "confirm_city_yes", "text": "Sí, es correcta"},
                    {"id": "confirm_city_no", "text": "No, corregir"}
                ]
            )
        else:
            # Invalid city format
            send_whatsapp_message(
                phone_number=message.get('from'),
                message="Por favor ingrese una ciudad válida:"
            )
    else:
        # Not a text message, ask again
        request_city(message, user)

def confirm_city(message, user):
    """Handle city confirmation"""
    if message.get('type') == 'interactive':
        interactive = message.get('interactive', {})
        if interactive.get('type') == 'button_reply':
            button_id = interactive.get('button_reply', {}).get('id', '')
            
            if button_id == "confirm_city_yes":
                # City confirmed, complete the process
                user_table.update_item(
                    Key={'phone': message.get('from')},
                    UpdateExpression="SET #status = :status, #signup = :signup",
                    ExpressionAttributeNames={'#status': 'status', '#signup': 'signup'},
                    ExpressionAttributeValues={':status': None, ':signup': True}
                )
                user["status"] = None
                logger.info(f"User completed signup: {message.get('from')}")
                proccess_auction(message, user)
            elif button_id == "confirm_city_no":
                # City not confirmed, ask again
                user_table.update_item(
                    Key={'phone': message.get('from')},
                    UpdateExpression="SET #status = :status",
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': 'pending_city'}
                )
                user["status"] = "pending_city"
                request_city(message, user)
    else:
        # Not an interactive message, ask again for confirmation
        city = user.get('city', '')
        send_whatsapp_message(
            phone_number=message.get('from'),
            message=f"¿Es correcta su ciudad: {city}?",
            buttons=[
                {"id": "confirm_city_yes", "text": "Sí, es correcta"},
                {"id": "confirm_city_no", "text": "No, corregir"}
            ]
        )
