import flask
from flask import request
import os
from bot import Bot, ObjectDetectionBot
import boto3
from botocore.exceptions import ClientError
import logging

app = flask.Flask(__name__)

# TODO load TELEGRAM_TOKEN value from Secret Manager

# Load TELEGRAM_TOKEN from Secret Manager
secret_name = "gershon-secrets.env"
region_name = "us-east-2"
session = boto3.session.Session()
client = session.client(service_name='secretsmanager', region_name=region_name)
TELEGRAM_TOKEN = client.get_secret_value(SecretId=secret_name)['SecretString']

def get_secret(secret_name, region_name):
    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager', region_name=region_name)

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        logging.error(f"Error retrieving secret '{secret_name}' from AWS Secrets Manager: {e}")
        raise e

    return get_secret_value_response['SecretString']


TELEGRAM_APP_URL = os.environ['TELEGRAM_APP_URL']

# Initialize ObjectDetectionBot
bot = ObjectDetectionBot(TELEGRAM_TOKEN, TELEGRAM_APP_URL)

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

    # TODO use the prediction_id to retrieve results from DynamoDB and send to the end-user

    chat_id = ...
    text_results = ...

    bot.send_text(chat_id, text_results)
    return 'Ok'


@app.route(f'/loadTest/', methods=['POST'])
def load_test():
    req = request.get_json()
    bot.handle_message(req['message'])
    return 'Ok'


if __name__ == "__main__":
    bot = ObjectDetectionBot(TELEGRAM_TOKEN, TELEGRAM_APP_URL)

    app.run(host='0.0.0.0', port=8443)
