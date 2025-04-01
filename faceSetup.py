import boto3, yaml, os, time
import crudCFTemplate, crudDynamo, crudLambdaFunction, crudS3

def main():
    # Global naming configuration
    APPLICATION = "face"
    USER_ID = "s2131971"
    USER_EMAIL = "john.doe@example.com"

    if USER_EMAIL == "john.doe@example.com":
        raise ValueError("Default email is being used; email alerts will not work. Please update the USER_EMAIL to a valid address.")
    
    # Get AWS account and region context
    print("Retriveing infromation for resource naming")
    account_id = boto3.client('sts').get_caller_identity()['Account']
    region = boto3.session.Session().region_name
    
    # Resource name generator
    def resource_name(service: str) -> str:
        return f"{APPLICATION}{service}-{account_id}-{region}-{USER_ID}"

    # Initialise DynamoDB Table
    print("\nInitilising DynamoDB Table")
    table_name = resource_name("data")
    exisiting_table = crudDynamo.find_table(table_name)
    
    # Cleanup existing DynamoDB
    if exisiting_table:
        crudDynamo.delete_table(table_name)
    
    dynamo_response = crudDynamo.create_table(
        table_name=table_name,
        partition_key="id",
    )
    
    # Initialise CloudFormation Stack
    print("\nInitilising CloudFormation Stack")
    stack_name = resource_name("queuebucket")
    existing_stack = crudCFTemplate.find_stack(stack_name)
    
    # Cleanup existing CloudFormation Stack
    if existing_stack:
        try:
            # Empty S3 bucket before deletion
            bucket_name = crudCFTemplate.get_stack_output(existing_stack, "S3BucketName")
            crudS3.empty_bucket(bucket_name)
        except ValueError as e:
            print(f"No bucket to empty: {str(e)}")
            
        crudCFTemplate.delete_stack(stack_name)

    # Define names of services created by the template
    stack_params = [
        {'ParameterKey': 'BucketName', 'ParameterValue': resource_name("bucket")},
        {'ParameterKey': 'QueueName', 'ParameterValue': resource_name("queue")},
        {'ParameterKey': 'TopicName', 'ParameterValue': resource_name("topic")},
        {'ParameterKey': 'TopicEmail', 'ParameterValue': USER_EMAIL}
    ]
    
    stack = crudCFTemplate.create_stack(
        stack_name=stack_name,
        template_path=os.path.join("Templates", "QueueBucket.yaml"),
        parameters=stack_params
    )

    # Get stack ARN outputs
    sqs_arn = crudCFTemplate.get_stack_output(stack, 'SQSArn')
    sns_topic_arn = crudCFTemplate.get_stack_output(stack, 'SNSTopicArn')
    stream_arn = dynamo_response['LatestStreamArn']
    if not stream_arn:
        raise ValueError("DynamoDB stream ARN not found")
        
    # Lambda Configuration
    lambda_role = f"arn:aws:iam::{account_id}:role/LabRole"
    
    # Email Alert Lambda
    print("\nInitilising Lambda email alert function")
    email_lambda_name = resource_name("lambdaemail")
    exisiting_email_function = crudLambdaFunction.find_lambda_function(email_lambda_name)
    
    if exisiting_email_function:
        crudLambdaFunction.delete_lambda_function(email_lambda_name)
        
    crudLambdaFunction.create_lambda_function(
        function_name=email_lambda_name,
        code_path=os.path.join("Templates", "EmailLambdaFunction.py"),
        role_arn=lambda_role,
        handler="EmailLambdaFunction.lambda_handler",
        runtime="python3.13",
        environment={'SNS_TOPIC_ARN': sns_topic_arn}
    )
    crudLambdaFunction.create_event_source(email_lambda_name, stream_arn)

    # Face Processing Lambda
    print("\nInitilising Lambda rekognition function")
    face_lambda_name = resource_name("lambdarek")
    exisiting_rek_function = crudLambdaFunction.find_lambda_function(face_lambda_name)
    
    if exisiting_rek_function:
        crudLambdaFunction.delete_lambda_function(face_lambda_name)

    crudLambdaFunction.create_lambda_function(
        function_name=face_lambda_name,
        code_path=os.path.join("Templates", "RekognitionLambdaFunction.py"),
        role_arn=lambda_role,
        handler="RekognitionLambdaFunction.lambda_handler",
        runtime="python3.13",
        environment={'SOURCE_IMAGE': 'images/groupphoto.png', 'DYNAMODB_TABLE': table_name}
    )
    crudLambdaFunction.create_event_source(face_lambda_name, sqs_arn)

    # Upload to S3
    time.sleep(10)
    print("\nUploading image files to S3 Bucket")
    bucket_name = crudCFTemplate.get_stack_output(stack, "S3BucketName")
    crudS3.upload_to_s3(bucket_name)

if __name__ == "__main__":
    main()