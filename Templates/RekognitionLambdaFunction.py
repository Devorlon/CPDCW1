import json
import boto3
import os
from datetime import datetime

s3_client = boto3.client('s3')
rekognition_client = boto3.client('rekognition')
dynamodb = boto3.resource('dynamodb')

# Get environment variables
TABLE_NAME = os.environ['DYNAMODB_TABLE']
table = dynamodb.Table(TABLE_NAME)

def lambda_handler(event, context):
    SOURCE_IMAGE = os.environ.get('SOURCE_IMAGE', 'images/groupphoto.png')
    
    for sqs_record in event.get('Records', []):
        try:
            s3_event = json.loads(sqs_record['body'])
            
            # Skip test events
            if 'Event' in s3_event and s3_event['Event'] == 's3:TestEvent':
                print("Skipping S3 test event")
                continue

            # Get bucket and image key for processing    
            record = s3_event['Records'][0]
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            
            # Skip processing groupphoto.png
            if key == SOURCE_IMAGE:
                print(f"Skipping source image: {key}")
                continue
            
            print(f"Processing image: {key}")
            
            # Face Comparison
            try:
                comp_response = rekognition_client.compare_faces(
                    SourceImage={'S3Object': {'Bucket': bucket, 'Name': key}},
                    TargetImage={'S3Object': {'Bucket': bucket, 'Name': SOURCE_IMAGE}},
                    SimilarityThreshold=70
                )
                
                # Get highest similarity
                max_similarity = 0
                for match in comp_response.get('FaceMatches', []):
                    similarity = match.get('Similarity', 0)
                    if similarity > max_similarity:
                        max_similarity = int(similarity)

                print(f"Comparison Response: {comp_response}\n Max Similarity: {max_similarity}")
            except Exception as e:
                print(f"Error in face comparison for {key}: {str(e)}")
                max_similarity = 0  # Default value on failure
            
            # Image Properties
            try:
                labels_response = rekognition_client.detect_labels(
                    Image={'S3Object': {'Bucket': bucket, 'Name': key}},
                    Features=['IMAGE_PROPERTIES'],
                    Settings={'ImageProperties': {'MaxDominantColors': 20}}
                )
                
                # Extract brightness values
                print(f"Labels Response: {labels_response}")
                image_properties = labels_response.get('ImageProperties', {})
                foreground_brightness = int(image_properties.get('Foreground', {}).get('Quality', {}).get('Brightness', 0))
                background_brightness = int(image_properties.get('Background', {}).get('Quality', {}).get('Brightness', 0))
                
            except Exception as e:
                print(f"Error in image properties detection for {key}: {str(e)}")
                foreground_brightness = 0
                background_brightness = 0
            
            # Save to DynamoDB
            try:
                item = {
                    'id': key,
                    'timestamp': datetime.utcnow().isoformat(),
                    'highestSimilarity': max_similarity,
                    'foregroundBrightness': foreground_brightness,
                    'backgroundBrightness': background_brightness,
                }
                
                table.put_item(Item=item)
                print(f"Saved results for {key} to DynamoDB")
                
            except Exception as e:
                print(f"Failed to save results for {key}: {str(e)}")
                
        except Exception as e:
            print(f"Error processing SQS record: {str(e)}")
            continue
    
    return {
        'statusCode': 200,
        'body': json.dumps('Processing completed')
    }