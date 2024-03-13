import json
import time
from pathlib import Path
import requests
from detect import run
import yaml
from loguru import logger
import boto3
from decimal import Decimal


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

images_bucket = 'gershonm-s3'
queue_name = 'Gershonm-sqs-Aws'
sqs_client = boto3.client('sqs', region_name='us-east-2')

with open("data/coco128.yaml", "r") as stream:
    names = yaml.safe_load(stream)['names']


def consume():
    try:
        while True:
            response = sqs_client.receive_message(QueueUrl=queue_name, MaxNumberOfMessages=1, WaitTimeSeconds=5)
            logger.info(f'response: {response}')
            if 'Messages' in response:
                message = response['Messages'][0]['Body'].split(' ')[0]
                receipt_handle = response['Messages'][0]['ReceiptHandle']

                msg_body = json.loads(response['Messages'][0]['Body'])

                prediction_id = response['Messages'][0]['MessageId']
                logger.info(f'message: {message}')
                logger.info(f'prediction: {prediction_id}. start processing')

                logger.info(f'Received message: {message}, processing prediction: {prediction_id}')

                img_name = msg_body["s3_key"]
                chat_id = msg_body["chat_id"]
                original_img_path = img_name.split("/")[-1]
                s3_client = boto3.client('s3')
                s3_client.download_file(images_bucket, img_name, original_img_path)

                logger.info(f'Downloaded image: {original_img_path}')

                run(
                    weights='yolov5s.pt',
                    data='data/coco128.yaml',
                    source=original_img_path,
                    project='static/data',
                    name=prediction_id,
                    save_txt=True
                )

                logger.info(f'prediction: {prediction_id}/{original_img_path}. done')

                predicted_img_path = Path(f'static/data/{prediction_id}/{original_img_path}')
                predicted_img_name = f'predicted_{original_img_path}'
                logger.info(f'before upload, gonna upload {predicted_img_path} with filename {predicted_img_name}')
                s3_client.upload_file(predicted_img_path, images_bucket, predicted_img_name)
                logger.info(f'Upload successful')

                pred_summary_path = Path(f'static/data/{prediction_id}/labels/{original_img_path.split(".")[0]}.txt')
                if pred_summary_path.exists():
                    with open(pred_summary_path) as f:
                        labels = f.read().splitlines()
                        labels = [line.split(' ') for line in labels]
                        labels = [{
                            'class': names[int(l[0])],
                            'cx': float(l[1]),
                            'cy': float(l[2]),
                            'width': float(l[3]),
                            'height': float(l[4]),
                        } for l in labels]

                    labels_dict = {}
                    for label in labels:
                        labels_dict[label['class']] = labels_dict.get(label['class'], 0) + 1

                    summary_label = ' '.join([f"{key}: {value}" for key, value in labels_dict.items()])

                    logger.info(f'Summary labels: {summary_label}')

                    db_labels = json.loads(json.dumps(labels), parse_float=Decimal)
                    prediction_summary = {
                        'prediction_id': prediction_id,
                        'original_img_path': original_img_path,
                        'predicted_img_path': predicted_img_name,
                        'labels': db_labels,
                        'time': Decimal(time.time()),
                        'detected_objects': summary_label,
                        'chat_id': chat_id
                    }
                    logger.info(f'prediction summery:\n\n {prediction_summary}')
                    dynamodb = boto3.resource('dynamodb', region_name='us-west-2')
                    table_name = 'Gershonm-polybot_AWS'
                    table = dynamodb.Table(table_name)
                    table.put_item(Item=prediction_summary)

                    logger.info(f'Stored prediction summary in DynamoDB')
                    logger.info(f'before post')
                    requests.get(
                        f'https://gershon-bot.devops-int-college.com:443/results/?predictionId={prediction_id}&chatId={chat_id}')
                    logger.info(f'after post')

                time.sleep(7)
                logger.info(f'Notified Polybot about prediction completion')
                sqs_client.delete_message(QueueUrl=queue_name, ReceiptHandle=receipt_handle)
                logger.info(f'Deleted message from queue')

    except KeyboardInterrupt:
        logger.info("Script interrupted. Exiting gracefully.")
        # Optionally perform cleanup operations before exiting


if __name__ == "__main__":
    consume()