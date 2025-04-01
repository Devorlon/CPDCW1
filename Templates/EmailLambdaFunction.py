import os
import boto3

sns = boto3.client('sns')

def lambda_handler(event, context):
    topic_arn = os.environ['SNS_TOPIC_ARN']
    alerts = []
    
    for record in event['Records']:
        try:
            if record['eventName'] in ['INSERT', 'MODIFY']:
                new_image = record['dynamodb']['NewImage']
                
                # Extract image name (id)
                image_id = new_image['id']['S']  # 'S' indicates string type
                
                # Extract metrics
                bb = int(new_image['backgroundBrightness']['N'])
                hs = int(new_image['highestSimilarity']['N'])
                
                if bb < 10 and hs < 55:
                    alerts.append(f'Image: {image_id} - Low values detected (Brightness: {bb}, Similarity: {hs})')
            
            print(f"Processed: {image_id}, (Brightness: {bb}, Similarity: {hs})")
        except Exception as e:
            print(f"Error processing record: {str(e)}")
    
    if alerts:
        message = "\n".join(alerts)
        sns.publish(
            TopicArn=topic_arn,
            Message=message,
            Subject='Security Alert Notification'
        )
    
    return f"Processed {len(event['Records'])} records"