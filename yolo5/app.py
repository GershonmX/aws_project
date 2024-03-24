import json
import time
from pathlib import Path
import requests
from detect import run
import yaml
from loguru import logger
import boto3
from decimal import Decimal

# AWS Configuration
kms_key_id = "b194d0e3-4919-4449-a478-b6a4a0960864"
sqs_client = boto3.client('sqs', region_name='us-east-2')
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
images_bucket = 'gershonm-s3'
queue_name = 'Gershonm-sqs-Aws'

# Load COCO names
with open("data/coco128.yaml", "r") as stream:
    names = yaml.safe_load(stream)['names']


def consume():
    try:
        while True:
            response = sqs_client.receive_message(QueueUrl=queue_name, MaxNumberOfMessages=1, WaitTimeSeconds=5)
            if 'Messages' in response:
                message = response['Messages'][0]['Body'].split(' ')[0]
                receipt_handle = response['Messages'][0]['ReceiptHandle']
                msg_body = json.loads(response['Messages'][0]['Body'])
                prediction_id = response['Messages'][0]['MessageId']
                logger.info(f"Received message: {message}, processing prediction: {prediction_id}")

                # Download image from S3
                img_name = msg_body["s3_key"]
                original_img_path = img_name.split("/")[-1]
                s3_client.download_file(images_bucket, img_name, original_img_path)
                logger.info(f'Downloaded image: {original_img_path}')

                # Run detection
                run(
                    weights='yolov5s.pt',
                    data='data/coco128.yaml',
                    source=original_img_path,
                    project='static/data',
                    name=prediction_id,
                    save_txt=True
                )

                # Upload predicted image to S3
                predicted_img_path = Path(f'static/data/{prediction_id}/{original_img_path}')
                predicted_img_name = f'predicted_{original_img_path}'
                s3_client.upload_file(str(predicted_img_path), images_bucket, predicted_img_name)
                logger.info(f'Uploaded predicted image: {predicted_img_name}')

                # Process labels and summary
                pred_summary_path = Path(f'static/data/{prediction_id}/labels/{original_img_path.split(".")[0]}.txt')
                if pred_summary_path.exists():
                    with open(pred_summary_path) as f:
                        labels = f.read().splitlines()
                        labels = [line.split(' ') for line in labels]
                        labels_dict = {names[int(l[0])]: len(l) for l in labels}

                    summary_label = ' '.join([f"{key}: {value}" for key, value in labels_dict.items()])
                    logger.info(f'Summary labels: {summary_label}')

                    # Store prediction summary in DynamoDB
                    table_name = 'Gershonm-polybot_AWS'
                    table = dynamodb.Table(table_name)
                    prediction_summary = {
                        'prediction_id': prediction_id,
                        'original_img_path': original_img_path,
                        'predicted_img_path': predicted_img_name,
                        'labels': json.loads(json.dumps(labels), parse_float=Decimal),
                        'time': Decimal(time.time()),
                        'detected_objects': summary_label,
                        'chat_id': msg_body["chat_id"]
                    }
                    table.put_item(Item=prediction_summary)
                    logger.info(f'Stored prediction summary in DynamoDB')

                    # Notify Polybot about prediction completion
                    post_url = f'https://gershon-bot.devops-int-college.com:443/results/?predictionId={prediction_id}'
                    requests.get(url=post_url)
                    logger.info(f'Notified Polybot about prediction completion')

                # Delete message from SQS queue
                sqs_client.delete_message(QueueUrl=queue_name, ReceiptHandle=receipt_handle)
                logger.info(f'Deleted message from queue')

    except KeyboardInterrupt:
        logger.info("Script interrupted. Exiting gracefully.")
    except Exception as e:
        logger.error(f"An error occurred: {e}")


if __name__ == "__main__":
    consume()
