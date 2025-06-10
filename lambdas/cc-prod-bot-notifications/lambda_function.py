import json
from modules.sns import verify_subscription
from modules.whatsapp import send_whatsapp_template
import logging

# Configure logging
logger = logging.getLogger()

def lambda_handler(event, context):
    # Endpoint that acts as SNS subscription confirmation and message processor
    # Check if the event is a subscription confirmation
    if event.get('body') and 'Token' in event['body']:
        return verify_subscription(event)
    else:
        # Process the message
        return process_post(event)

def process_post(event):
    logger.info("Event received: %s", json.dumps(event))

    # get the phone number from the query string
    phone_number = event['queryStringParameters'].get('phone')

    # get the topic message from the body
    body = json.loads(event['body'])
    message = json.loads(body.get('Message'))
    if phone_number != message.get('phone'):
        send_whatsapp_template(
            phone_number=phone_number,
            template_name="new_offer",
            template_language="es",
            template_params=[message.get('amount')]
        )
    return {
        'statusCode': 200,
        'body': json.dumps({'status': 'success'})
    }