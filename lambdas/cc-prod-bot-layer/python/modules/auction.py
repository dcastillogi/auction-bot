import boto3
import logging
import os
from datetime import datetime
import pytz
from boto3.dynamodb.conditions import Key
from modules.whatsapp import send_whatsapp_message
from modules.sns import add_subscription, remove_subscription, publish_message
from decimal import Decimal
import uuid

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
user_table = dynamodb.Table('cc-prod-bot-user')
bid_table = dynamodb.Table('cc-prod-bot-bid')
state_table = dynamodb.Table('cc-prod-bot-state')

MIN_BID = float(os.environ.get("MIN_BID"))
MIN_BID_DIFFERENCE = float(os.environ.get("MIN_BID_DIFFERENCE"))
PROPERTY_ADDRESS = os.environ.get("PROPERTY_ADDRESS")
MAX_BID = float(os.environ.get("MAX_BID"))

# Set timezone (adjust to your local timezone)
timezone = pytz.timezone('America/Bogota')
INITIAL_HOUR = datetime.fromisoformat(os.environ.get("INITIAL_HOUR")).astimezone(timezone)
FINAL_HOUR = datetime.fromisoformat(os.environ.get("FINAL_HOUR")).astimezone(timezone)

def proccess_auction(message, user):
    # Get current time with timezone
    now = datetime.now(timezone)
    
    if now < INITIAL_HOUR:
        logger.info("Auction has not started yet.")
        send_whatsapp_message(
            phone_number=message.get('from'),
            message=f"La subasta aún no ha comenzado. Estará disponible el {INITIAL_HOUR.strftime('%Y-%m-%d a las %H:%M')}."
        )
        return
    elif now > FINAL_HOUR:
        logger.info("Auction has already ended.")
        send_whatsapp_message(
            phone_number=message.get('from'),
            message="La subasta ha concluido. Agradecemos su interés."
        )
        return
    
    # Get highest offer from bid_table using GSI partition key "phone" and sort key "amount"
    response = state_table.get_item(
        Key={
            'id': 'HIGHEST_BID'
        }
    )
    highest_offer = float(response.get('Item', {}).get('amount', 0))
    highest_offer_phone = response.get('Item', {}).get('phone', None)
    logger.info(f"Highest offer: {highest_offer}")

    # Check user last message
    last_message = user.get("last_message")

    # If the last message is older than 15 minutes, update the status to None
    if last_message and (now.timestamp() - int(last_message) > 900):
        user['status'] = None
        user_table.update_item(
            Key={'phone': message.get('from')},
            UpdateExpression="SET #status = :status",
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':status': None}
        )
        logger.info("User status updated to None due to inactivity.")

    

    if user.get("status") == "pending_offer_confirmation":
        # Get user's draft bid
        draft_bid = user.get("draft_bid")
        # Confirm offer
        if message.get("interactive"):
            if message.get("interactive").get("button_reply"):
                button_id = message.get("interactive").get("button_reply").get("id")
                
                if button_id == "confirm_offer":
                    if highest_offer > draft_bid:
                        # User is not the highest bidder
                        send_whatsapp_message(
                            phone_number=message.get('from'),
                            message=f"Su oferta de {format_as_money(draft_bid)} no es la más alta. La oferta más alta es de {format_as_money(highest_offer)}. Por favor, realice una nueva oferta."
                        )
                        # Update user status to None
                        user_table.update_item(
                            Key={'phone': message.get('from')},
                            UpdateExpression="SET #status = :status, #draft_bid = :bid",
                            ExpressionAttributeNames={'#status': 'status', '#draft_bid': 'draft_bid'},
                            ExpressionAttributeValues={':status': None, ':bid': None}
                        )
                        send_menu(message, user, highest_offer, highest_offer_phone)
                        return
                    if draft_bid < MIN_BID or draft_bid > MAX_BID:
                        # User's bid is out of range
                        send_whatsapp_message(
                            phone_number=message.get('from'),
                            message=f"Su oferta de {format_as_money(draft_bid)} no es válida. Debe estar entre {format_as_money(MIN_BID)} y {format_as_money(MAX_BID)}."
                        )
                        # Update user status to None
                        user_table.update_item(
                            Key={'phone': message.get('from')},
                            UpdateExpression="SET #status = :status, #draft_bid = :bid",
                            ExpressionAttributeNames={'#status': 'status', '#draft_bid': 'draft_bid'},
                            ExpressionAttributeValues={':status': None, ':bid': None}
                        )
                        send_menu(message, user, highest_offer, highest_offer_phone)
                        return

                    # Save the offer in the bid_table
                    bid_table.put_item(
                        Item={
                            'phone': message.get('from'),
                            'amount': Decimal(str(draft_bid)),
                            'timestamp': int(now.timestamp()),
                            'id': str(uuid.uuid4())
                        }
                    )
                    # Save the highest offer in the state_table
                    state_table.update_item(
                        Key={
                            'id': 'HIGHEST_BID'
                        },
                        UpdateExpression="SET #amount = :amount, #phone = :phone",
                        ExpressionAttributeNames={'#amount': 'amount', '#phone': 'phone'},
                        ExpressionAttributeValues={':amount': Decimal(str(draft_bid)), ':phone': message.get('from')}
                    )
                    # Update user status to None
                    user_table.update_item(
                        Key={'phone': message.get('from')},
                        UpdateExpression="SET #status = :status, #draft_bid = :bid",
                        ExpressionAttributeNames={'#status': 'status', '#draft_bid': 'draft_bid'},
                        ExpressionAttributeValues={':status': None, ':bid': None}
                    )
                    logger.info(f"User {message.get('from')} made an offer of {draft_bid}.")
                    # Notify users
                    publish_message(
                        json_message={
                            'amount': format_as_money(draft_bid),
                            'phone': message.get('from')
                        },
                        subject="Nueva oferta registrada"
                    )
                    send_whatsapp_message(
                        phone_number=message.get('from'),
                        message=f"Su oferta de {format_as_money(draft_bid)} ha sido registrada. ¡Buena suerte!"
                    )
                    return
                elif button_id == "cancel_offer":
                    # Update user status to None
                    user_table.update_item(
                        Key={'phone': message.get('from')},
                        UpdateExpression="SET #status = :status",
                        ExpressionAttributeNames={'#status': 'status'},
                        ExpressionAttributeValues={':status': None}
                    )
                    send_menu(message, user, highest_offer, highest_offer_phone)
                    return
        else:
            send_whatsapp_message(
                    phone_number=message.get('from'),
                    message=f"¿Desea confirmar su oferta de {format_as_money(draft_bid)}?",
                    buttons=[
                        {"id": "confirm_offer", "text": "Sí"},
                        {"id": "cancel_offer", "text": "No"}
                    ]
                )
    elif user.get("status") == "pending_notification_configuration":
        # Enable or disable notifications
        if message.get("interactive"):
            if message.get("interactive").get("button_reply"):
                button_id = message.get("interactive").get("button_reply").get("id")
                if button_id == "enable_notifications":
                    # Update user status to None and enable notifications
                    if not user.get("sns_subscription"):
                        sns_subscription = add_subscription(
                            phone=message.get('from')
                        )
                        if not sns_subscription:
                            send_whatsapp_message(
                                phone_number=message.get('from'),
                                message="No se pudo habilitar la suscripción a las notificaciones. Por favor, inténtelo más tarde."
                            )
                            return

                        user_table.update_item(
                            Key={'phone': message.get('from')},
                            UpdateExpression="SET #status = :status, #sns_subscription = :sub",
                            ExpressionAttributeNames={'#status': 'status', '#sns_subscription': 'sns_subscription'},
                            ExpressionAttributeValues={':status': None, ':sub': sns_subscription}
                        )
                    else:
                        # Update user status to None
                        user_table.update_item(
                            Key={'phone': message.get('from')},
                            UpdateExpression="SET #status = :status",
                            ExpressionAttributeNames={'#status': 'status'},
                            ExpressionAttributeValues={':status': None}
                        )
                    send_whatsapp_message(
                        phone_number=message.get('from'),
                        message="Las notificaciones han sido habilitadas. ¡Buena suerte!"
                    )
                    
                    return
                elif button_id == "disable_notifications":
                    # Remove subscription from SNS
                    sns_subscription = user.get("sns_subscription")
                    if sns_subscription:
                        if not remove_subscription(
                            subscription_arn=sns_subscription
                        ):
                            send_whatsapp_message(
                                phone_number=message.get('from'),
                                message="No se pudo deshabilitar la suscripción a las notificaciones. Por favor, inténtelo más tarde."
                            )
                            return
                    # Update user status to None and disable notifications
                    user_table.update_item(
                        Key={'phone': message.get('from')},
                        UpdateExpression="SET #status = :status, #sns_subscription = :sub",
                        ExpressionAttributeNames={'#status': 'status', '#sns_subscription': 'sns_subscription'},
                        ExpressionAttributeValues={':status': None, ':sub': None}
                    )
                    send_whatsapp_message(
                        phone_number=message.get('from'),
                        message="Las notificaciones han sido deshabilitadas. ¡Buena suerte!"
                    )
                    return
    else:
        # Check if he click some interactive button
        if message.get("interactive"):
            if message.get("interactive").get("button_reply"):
                button_id = message.get("interactive").get("button_reply").get("id")
                if button_id == "manage_notifications":
                    send_whatsapp_message(
                        phone_number=message.get('from'),
                        message="¿Desea recibir notificaciones cuando haya nuevas ofertas?",
                        buttons=[
                            {"id": "enable_notifications", "text": "Sí"},
                            {"id": "disable_notifications", "text": "No"}
                        ]
                    )
                    # Update user status to pending_notification_configuration
                    user_table.update_item(
                        Key={'phone': message.get('from')},
                        UpdateExpression="SET #status = :status",
                        ExpressionAttributeNames={'#status': 'status'},
                        ExpressionAttributeValues={':status': 'pending_notification_configuration'}
                    )
                    return
                elif button_id == "offer":
                    # Check if the user is the same as the highest offer
                    if user.get("phone") == highest_offer_phone:
                        send_whatsapp_message(
                            phone_number=message.get('from'),
                            message="Usted es el oferente más alto. ¡Buena suerte!"
                        )
                        return
                    send_whatsapp_message(
                    phone_number=message.get('from'),
                    message=f"¿Esta seguro que desea ofertar {format_as_money(max(highest_offer + MIN_BID_DIFFERENCE, MIN_BID))}?",
                    buttons=[
                            {"id": "confirm_offer", "text": "Sí"},
                            {"id": "cancel_offer", "text": "No"}
                        ]
                    )
                    # Update user status to pending_offer_confirmation
                    user_table.update_item(
                    Key={'phone': message.get('from')},
                    UpdateExpression="SET #status = :status, #draft_bid = :bid",
                    ExpressionAttributeNames={'#status': 'status', '#draft_bid': 'draft_bid'},
                    ExpressionAttributeValues={':status': 'pending_offer_confirmation', ':bid': Decimal(str(max(highest_offer + MIN_BID_DIFFERENCE, MIN_BID)))}
                    )
                    return
        
        send_menu(message, user, highest_offer, highest_offer_phone)

def send_menu(message, user, highest_offer, highest_offer_phone):
    # User is in the auction process
    if user.get("phone") == highest_offer_phone:
        send_whatsapp_message(
            phone_number=message.get('from'),
            message="Usted es el oferente más alto. ¡Buena suerte! ¿Desea configurar próximas notificaciones?",
            buttons=[
                {"id": "manage_notifications", "text": "Notificaciones"}
            ]
        )
    elif highest_offer > 0:
        send_whatsapp_message(
            phone_number=message.get('from'),
            message=f"La subasta está en curso. La oferta más alta es de {format_as_money(highest_offer)}. ¿Desea realizar la próxima oferta por {format_as_money(highest_offer + MIN_BID_DIFFERENCE)} o configurar próximas notificaciones?",
            buttons=[
                {"id": "offer", "text": "Ofertar"},
                {"id": "manage_notifications", "text": "Notificaciones"}
            ]
        )
    else:
        send_whatsapp_message(
            phone_number=message.get('from'),
            message=f"La subasta está en curso. Hasta el momento no se ha realizado ninguna oferta. ¿Desea ofertar {format_as_money(MIN_BID)} o configurar próximas notificaciones?",
            buttons=[
                {"id": "offer", "text": "Ofertar"},
                {"id": "manage_notifications", "text": "Notificaciones"}
            ]
        )

def format_as_money(value):
    """
    Formatea un número como una cadena de dinero en formato colombiano.
    
    Args:
        value (float): El valor a formatear.
    
    Returns:
        str: El valor formateado como cadena de dinero.
    """
    return f"${value:,.0f}".replace(",", ".")