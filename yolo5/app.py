import json
import time
from pathlib import Path
import requests
from detect import run
import yaml
from loguru import logger
import os
import boto3
from decimal import Decimal

images_bucket = 'gershonm-s3'
queue_name = 'Gershonm-sqs-Aws'
sqs_client = boto3.client('sqs', region_name='us-east-2')

with open("data/coco128.yaml", "r") as stream:
    names = yaml.safe_load(stream)['names']


def consume():
    while True:
        response = sqs_client.receive_message(QueueUrl=queue_name, MaxNumberOfMessages=1, WaitTimeSeconds=5)

        if 'Messages' in response:

            # file_path = response['Messages'][0]
            message = response['Messages'][0]['Body'].split(' ')[0]
            receipt_handle = response['Messages'][0]['ReceiptHandle']

            # Use the ReceiptHandle as a prediction UUID
            prediction_id = response['Messages'][0]['MessageId']
            logger.info(f'message: {message}')
            logger.info(f'prediction: {prediction_id}. start processing')

            # Receives a URL parameter representing the image to download from S3
            img_name = message
            chat_id = response['Messages'][0]['Body'].split(' ')[1]
            original_img_path = img_name.split("/")[-1]
            s3_client = boto3.client('s3')
            logger.info(f'images_bucket {images_bucket} , img_name {img_name} ,'
                        f' original_img_path {original_img_path}')
            s3_client.download_file(images_bucket, img_name, original_img_path)
            # TODO download img_name from S3, store the local image path in original_img_path

            logger.info(f'prediction: {prediction_id}/{original_img_path}. Download img completed')

            # Predicts the objects in the image
            run(
                weights='yolov5s.pt',
                data='data/coco128.yaml',
                source=original_img_path,
                project='static/data',
                name=prediction_id,
                save_txt=True
            )

            logger.info(f'prediction: {prediction_id}/{original_img_path}. done')

            # This is the path for the predicted image with labels The predicted image typically includes bounding
            # boxes drawn around the detected objects, along with class labels and possibly confidence scores.
            predicted_img_path = Path(f'static/data/{prediction_id}/{original_img_path}')

            s3_client.upload_file(predicted_img_path, images_bucket, original_img_path)

            logger.info('upload success')

            # TODO Uploads the predicted image (predicted_img_path) to S3 (be careful not to override the original
            #  image).

            # Parse prediction labels and create a summary
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

                labels_dic = {}
                for label in labels:
                    try:
                        labels_dic[label['class']] += 1
                    except:
                        labels_dic.update({label['class']: 1})

                summary_label = ''
                for key in labels_dic.keys():
                    summary_label = summary_label + key + ": " + labels_dic[key].__str__() + " "

                logger.info(f'summary_label:    {summary_label}')

                logger.info(f'prediction: {prediction_id}/{original_img_path}. prediction summary:\n\n{labels}')
                db_labels = json.loads(json.dumps(labels), parse_float=Decimal)
                logger.info(f'db_labels', db_labels)
                logger.info(f'db_labels', json.dumps(labels))
                prediction_summary = {
                    'prediction_id': prediction_id,
                    'original_img_path': original_img_path,
                    'predicted_img_path': predicted_img_path.__str__(),
                    'labels': db_labels,
                    'time': Decimal(time.time()),
                    'detected_objects': summary_label
                }

                # TODO store the prediction_summary in a DynamoDB table

                dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
                table_name = 'Gershonm-polybot_AWS'
                table = dynamodb.Table(table_name)
                table.put_item(Item=prediction_summary)

                # TODO perform a GET request to Polybot to `/results` endpoint
            requests.get(
                f'gershon-LB1-2001611446.us-east-2.elb.amazonaws.com/results?predictionId/results?predictionId={prediction_id}'
                f'&chatId={chat_id}')
            # Delete the message from the queue as the job is considered as DONE
            sqs_client.delete_message(QueueUrl=queue_name, ReceiptHandle=receipt_handle)

        time.sleep(5)
if __name__ == "__main__":
    consume()