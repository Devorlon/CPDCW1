import os, tempfile, boto3, zipfile, time
from typing import Dict, Optional, List
from botocore.exceptions import ClientError


def create_lambda_function(function_name: str, code_path: str, role_arn: str, handler: str, runtime: str, environment: dict) -> dict:
    lambda_client = boto3.client('lambda')
    
    # Package code
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, 'lambda.zip')
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.write(code_path, arcname=os.path.basename(code_path))
        
        with open(zip_path, 'rb') as f:
            code_bytes = f.read()
    
    try:
        response = lambda_client.create_function(
            FunctionName=function_name,
            Runtime=runtime,
            Role=role_arn,
            Handler=handler,
            Code={'ZipFile': code_bytes},
            Timeout=60,
            Publish=True,
            Environment={'Variables': environment}
        )
        
        # Wait until function is active
        waiter = lambda_client.get_waiter('function_active')
        waiter.wait(FunctionName=function_name)
        
        print(f"Created Lambda Function {function_name}")
        return response
    
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceConflictException':
            raise ValueError(f"Function {function_name} already exists") from e
        else:
            print(f"Error creating Lambda Function {function_name}: {e}")
            raise

def delete_lambda_function(function_name: str) -> None:
    lambda_client = boto3.client('lambda')
    
    # Remove all event source mappings
    try:
        print(f"Deleting {function_name} source mappings")
        mappings = lambda_client.list_event_source_mappings(
            FunctionName=function_name
        )
        for mapping in mappings['EventSourceMappings']:
            lambda_client.delete_event_source_mapping(UUID=mapping['UUID'])
    except ClientError:
        pass
    
    # Delete function
    try:
        print(f"Deleting existing Lambda Function {function_name}")
        lambda_client.delete_function(FunctionName=function_name)
        
        # Sleep for 5s as there is no waiter for deleting a function
        time.sleep(5)
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return
        raise

def find_lambda_function(function_name: str) -> Optional[dict]:
    lambda_client = boto3.client('lambda')
    try:
        lambda_function = lambda_client.get_function(FunctionName=function_name)
        print(f"Found {function_name}")
        return lambda_function
    except ClientError as e:
        print(f"Error searching for {function_name}")
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return None
        else:
            print(f"Error finding Lambda Function: {function_name}")
            raise

def create_event_source(function_name: str, event_source_arn: str) -> dict:
    lambda_client = boto3.client('lambda')
    
    # Validate ARN format first
    if not event_source_arn.startswith('arn:aws:'):
        raise ValueError(f"Invalid event source ARN: {event_source_arn}")
        
    delete_event_source(lambda_client, function_name, event_source_arn)

    # Create new mapping with manual state checks
    params = {
        'EventSourceArn': event_source_arn,
        'FunctionName': function_name,
        'Enabled': True,
        'BatchSize': 10
    }
    
    if any(s in event_source_arn for s in [':dynamodb:', ':kinesis:']):
        params['StartingPosition'] = 'LATEST'

    try:
        response = lambda_client.create_event_source_mapping(**params)
        uuid = response['UUID']
        
        # Wait for active state with manual polling
        max_retries = 10
        for _ in range(max_retries):
            status = lambda_client.get_event_source_mapping(UUID=uuid)
            state = status['State']
            
            if state in ['Enabled', 'Active']:
                print(f"Mapping {uuid} is active")
                break
            if state == 'CreateFailed':
                raise RuntimeError(f"Creation failed: {status.get('StateTransitionReason', 'Unknown error')}")
            
            print(f"Current state: {state}, waiting...")
            time.sleep(30)
        else:
            raise TimeoutError("Timed out waiting for mapping activation")
            
        return response
        
    except ClientError as e:
        print(f"Error creating event source mapping: {e}")
        raise
    
def delete_event_source(lambda_client ,function_name: str, event_source_arn: str) -> bool:
    # Remove existing mappings with manual state polling
    existing_mappings = []
    paginator = lambda_client.get_paginator('list_event_source_mappings')
    
    try:
        for page in paginator.paginate(FunctionName=function_name, EventSourceArn=event_source_arn):
            existing_mappings.extend(page['EventSourceMappings'])
    except ClientError as e:
        print(f"Error listing event sources: {e}")
        raise

    for mapping in existing_mappings:
        uuid = mapping['UUID']
        current_state = mapping['State']
        
        # Handle transitional states manually
        while current_state in ['Creating', 'Updating', 'Deleting']:
            print(f"Waiting for {uuid} to exit transitional state ({current_state})...")
            time.sleep(2)
            try:
                mapping = lambda_client.get_event_source_mapping(UUID=uuid)
                current_state = mapping['State']
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    break
                raise

        if current_state in ['Enabled', 'Disabled', 'CreateFailed']:
            try:
                print(f"Deleting mapping {uuid} (state: {current_state})")
                lambda_client.delete_event_source_mapping(UUID=uuid)
                
                # Poll until deleted
                while True:
                    time.sleep(60)
                    try:
                        lambda_client.get_event_source_mapping(UUID=uuid)
                    except ClientError as e:
                        if e.response['Error']['Code'] == 'ResourceNotFoundException':
                            print(f"Mapping {uuid} successfully deleted")
                            break
                        raise
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceInUseException':
                    print(f"Mapping {uuid} still in use, retrying...")
                    time.sleep(5)
                    continue
                raise

def list_lambda_functions() -> List[str]:
    lambda_client = boto3.client('lambda')
    funcs = []
    paginator = lambda_client.get_paginator('list_functions')
    
    for page in paginator.paginate():
        funcs.extend([f['FunctionName'] for f in page['Functions']])
    
    return funcs