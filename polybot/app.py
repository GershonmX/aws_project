import flask
from flask import request
import os
from bot import ImageProcessingBot
import boto3
from botocore.exceptions import ClientError
import json

app = flask.Flask(__name__)


def get_secret():
    secret_name = "gershon-secrets.env"
    region_name = "us-east-2"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    secret = get_secret_value_response['SecretString']
    return json.loads(secret)


# load TELEGRAM_TOKEN value from Secret Manager
secrets = get_secret()
TELEGRAM_TOKEN = secrets["TELEGRAM_TOKEN"]  # os.environ['TELEGRAM_TOKEN']

TELEGRAM_APP_URL = secrets["TELEGRAM_APP_URL"]  # os.environ['TELEGRAM_APP_URL']


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
    # Initialize the DynamoDB client
    dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
    table_name = 'Gershonm-polybot_AWS'  # Replace with your table name
    table = dynamodb.Table(table_name)

    # Define your primary key
    primary_key = {
        'prediction_id': str(prediction_id)
        # Replace with the actual primary key attribute name and value
    }

    # Use the get_item method to fetch the item
    response = table.get_item(Key=primary_key)

    # Check if the item was found
    if 'Item' in response:
        item = response['Item']
        print("Item found:")
        print(item['detected_objects'])
        print(item['chat_id'])

    else:
        print("Item not found")

    chat_id = item['chat_id']
    text_results = item['detected_objects']

    bot.send_text(chat_id, text_results)
    return 'Ok'


@app.route(f'/loadTest/', methods=['POST'])
def load_test():
    req = request.get_json()
    bot.handle_message(req['message'])
    return 'Ok'


if __name__ == "__main__":
    bot = ImageProcessingBot(TELEGRAM_TOKEN, TELEGRAM_APP_URL)

    app.run(host='0.0.0.0', port=8443)