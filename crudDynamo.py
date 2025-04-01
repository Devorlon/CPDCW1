import boto3
from typing import Optional, Dict, Any
from botocore.exceptions import ClientError

def create_table(table_name: str, partition_key: str) -> dict:
    dynamodb = boto3.resource('dynamodb')
    
    # Setting the 
    key_schema = [{'AttributeName': partition_key, 'KeyType': 'HASH'}]
    attribute_defs = [{'AttributeName': partition_key, 'AttributeType': 'S'}]
    
    # Parameters for table creation and enabling email notifications 
    params = {
        'TableName': table_name,
        'KeySchema': key_schema,
        'AttributeDefinitions': attribute_defs,
        'ProvisionedThroughput': {
            'ReadCapacityUnits': 5,
            'WriteCapacityUnits': 5
        },
        'StreamSpecification': {
            'StreamEnabled': True,
            'StreamViewType': 'NEW_IMAGE'
        }
    }
    
    try:
        print(f"Creating DynamoDB Table {table_name}")
        table = dynamodb.create_table(**params)
        
        # Refresh table attributes to get stream ARN
        table.wait_until_exists()
        table.load()
        print(f"Table '{table_name}' created successfully")
        return {
            'TableArn': table.table_arn,
            'LatestStreamArn': table.latest_stream_arn
        }
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            print(f"Table '{table_name}' already exists")
        else:
            print(f"Error creating table: {e.response['Error']['Message']}")
        raise

def find_table(table_name: str) -> Optional[dict]:
    dynamodb = boto3.client('dynamodb')
    try:
        response = dynamodb.describe_table(TableName=table_name)
        print(f"Found {table_name}")
        return response['Table']
    except ClientError as e:
        print(f"Error searching for {table_name}")
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return None
        raise

def delete_table(table_name: str) -> dict:
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)
    
    try:
        print(f"Deleting existing DynamoDB Table {table_name}")
        response = table.delete()
        
        # Wait for deletion to complete
        table.wait_until_not_exists()
        print(f"Table '{table_name}' deleted successfully")
        return { 'TableStatus': 'DELETED' }
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"Table '{table_name}' does not exist")
        else:
            print(f"Error deleting table: {e.response['Error']['Message']}")
        raise
    
def find_tables() -> list:
    dynamodb = boto3.client('dynamodb')
    tables = []
    paginator = dynamodb.get_paginator('list_tables')
    
    try:
        for page in paginator.paginate():
            tables.extend(page.get('TableNames', []))
        return tables
    except Exception as e:
        print(f"Error retrieving tables: {str(e)}")
        return []