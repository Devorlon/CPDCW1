import boto3, os, zipfile, time
from typing import Optional, Dict, Any
from botocore.exceptions import ClientError

def empty_bucket(bucket_name: str) -> None:
    s3 = boto3.client('s3')
    
    try:
        # Delete all objects
        print(f"Emptying bucket: {bucket_name}")
        objects = s3.list_objects_v2(Bucket=bucket_name)
        if 'Contents' in objects:
            delete_keys = [{'Key': obj['Key']} for obj in objects['Contents']]
            s3.delete_objects(Bucket=bucket_name, Delete={'Objects': delete_keys})

        print(f"Bucket {bucket_name} emptied successfully")
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchBucket':
            print(f"Bucket {bucket_name} does not exist")
        else:
            print(f"Error emptying Bucket {bucket_name}")
            raise
        
def upload_to_s3(bucket_name: str) -> None:
    # Check if images.zip exists
    script_dir = os.path.dirname(os.path.abspath(__file__))
    zip_path = os.path.join(script_dir, 'images.zip')
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"images.zip not found at {zip_path}")
    
    # Extract images
    extract_dir = os.path.join(script_dir, 'extracted_images')
    os.makedirs(extract_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)
    
    # Upload files
    s3_client = boto3.client('s3')
    start_time = None
    
    for root, _, files in os.walk(extract_dir):
        for file_name in files:
            if start_time is not None:
                elapsed = time.time() - start_time
                if elapsed < 30:
                    time.sleep(30 - elapsed)
            
            start_time = time.time()
            file_path = os.path.join(root, file_name)
            relative_path = os.path.relpath(file_path, extract_dir)
            s3_key = relative_path.replace(os.path.sep, '/')
            
            s3_client.upload_file(Filename=file_path, Bucket=bucket_name, Key=s3_key)
            print(f"Uploaded {s3_key} to bucket {bucket_name}")
