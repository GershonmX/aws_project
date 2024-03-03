import flask
from flask import request
import os
from bot import ImageProcessingBot
import boto3
from botocore.exceptions import ClientError
import logging
import json

app = flask.Flask(__name__)

kms_key_id = "b194d0e3-4919-4449-a478-b6a4a0960864"
# Create a KMS client
kms_client = boto3.client('kms', region_name='us-east-2')
# Retrieve the key
response = kms_client.describe_key(KeyId=kms_key_id)
# The key details can be found in the 'KeyMetadata' field of the response
key_metadata = response['KeyMetadata']
TOKEN = key_metadata['Description']


# Load TELEGRAM_TOKEN value from Secret Manager
# secrets = get_secret()
TELEGRAM_TOKEN = TOKEN
TELEGRAM_APP_URL = "gershon-LB1-2001611446.us-east-2.elb.amazonaws.com"

@app.route('/', methods=['GET'])
def index():
    return 'Ok'

@app.route(f'/{TELEGRAM_TOKEN}/', methods=['POST'])
def webhook():
    req = request.get_json()
    bot.handle_message(req['message'])
    return 'Ok'

@app.route(f'/results/', methods=['GET'])
def results():
    prediction_id = request.args.get('predictionId')

    # Use the prediction_id to retrieve results from DynamoDB and send to the end-user
    dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
    table_name = 'Gershonm-polybot_AWS'
    table = dynamodb.Table(table_name)

    primary_key = {'prediction_id': str(prediction_id)}

    response = table.get_item(Key=primary_key)

    if 'Item' in response:
        item = response['Item']
        chat_id = item['chat_id']
        text_results = item['detected_objects']
        bot.send_text(chat_id, text_results)
        return 'Ok'
    else:
        return 'Item not found'

@app.route(f'/loadTest/', methods=['POST'])
def load_test():
    req = request.get_json()
    bot.handle_message(req['message'])
    return 'Ok'

if __name__ == "__main__":
    bot = ImageProcessingBot(TELEGRAM_TOKEN, TELEGRAM_APP_URL)
    app.run(host='0.0.0.0', port=8443)
