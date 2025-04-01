import boto3, os
from typing import Optional, Dict, Any
from botocore.exceptions import ClientError

def create_stack(stack_name: str, template_path: str, parameters: list) -> Dict[str, Any]:
    cf_client = boto3.client('cloudformation')
    
    # Validate and read template
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template file {template_path} not found")
    
    with open(template_path, 'r') as file:
        template_body = file.read()
    
    # Stack create parameters
    create_args = {
        'StackName': stack_name,
        'TemplateBody': template_body,
        'Capabilities': ['CAPABILITY_IAM'], # CAPABILITY_NAMED_IAM
        'Parameters': parameters
    }
    
    try:
        print(f"Creating CloudFormation Stack {stack_name}")
        
        response = cf_client.create_stack(**create_args)
        waiter = cf_client.get_waiter('stack_create_complete')
        waiter.wait(StackName=stack_name)
        
        # Return full stack details
        print(f"Stack creation completed. Status: {response}")
        return find_stack(stack_name)
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'AlreadyExistsException':
            raise ValueError(f"Stack {stack_name} already exists") from e
        else:
            print(f"Error creating Stack: {stack_name}")
            raise

def delete_stack(stack_name: str) -> None:
    cf_client = boto3.client('cloudformation')
    
    try:
        print(f"Deleting existing CloudFormation Stack {stack_name}")
        cf_client.delete_stack(StackName=stack_name)
        waiter = cf_client.get_waiter('stack_delete_complete')
        waiter.wait(StackName=stack_name)
        print(f"Stack {stack_name} deleted successfully")
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ValidationError':
            print(f"Stack {stack_name} does not exist")
        else:
            print(f"Error deleting Stack {stack_name}")
            raise

def find_stack(stack_name: str) -> Optional[dict]:
    cf_client = boto3.client('cloudformation')
    try:
        response = cf_client.describe_stacks(StackName=stack_name)
        print(f"Found {stack_name}")
        return response['Stacks'][0]
    except ClientError as e:
        print(f"Error searching for {stack_name}")
        if e.response['Error']['Code'] == 'ValidationError':
            return None
        else:
            print(f"Error finding Stack: {stack_name}")
            raise
    
def get_stack_output(stack: dict, output_key: str) -> str:
    # Return the service based on key
    for output in stack.get('Outputs', []):
        if output['OutputKey'] == output_key:
            return output['OutputValue']
    raise ValueError(f"Output '{output_key}' not found in stack {stack.get('StackName', 'UnknownStack')}")