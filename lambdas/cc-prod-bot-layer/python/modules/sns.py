import boto3
import os
import json
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)
sns_client = boto3.client('sns')

def verify_subscription(event):
    body = json.loads(event['body'])
    sns_client.confirm_subscription(
            TopicArn=os.environ['SNS_TOPIC_ARN'],
            Token=body.get('Token'),
    )
    return True
    
def add_subscription(phone):
    
    try:
        # Crear la suscripción
        response = sns_client.subscribe(
            TopicArn=os.environ['SNS_TOPIC_ARN'],
            Protocol='https',
            Endpoint=f"https://dvkd7854vh.execute-api.us-east-1.amazonaws.com/v1/notify?phone={phone}",
            ReturnSubscriptionArn=True
        )
        subscription_arn = response['SubscriptionArn']
        return subscription_arn
    except ClientError as e:
        logger.error(f"Error al crear la suscripción: {str(e)}")
        return False
    
def remove_subscription(subscription_arn):
    # Eliminar la suscripción
    try:
        sns_client.unsubscribe(
            SubscriptionArn=subscription_arn
        )
        return True
    except ClientError as e:
        logger.error(f"Error al eliminar la suscripción: {str(e)}")
        return False
    
def publish_message(json_message, subject):
    # Publicar un mensaje en el tema SNS
    try:
        response = sns_client.publish(
            TopicArn=os.environ['SNS_TOPIC_ARN'],
            Message=json.dumps(json_message),
            Subject=subject
        )
        return response
    except ClientError as e:
        logger.error(f"Error al publicar el mensaje: {str(e)}")
        return False