import boto3
import time
import subprocess
from pathlib import Path

# Configuration
KEY_PATH = '/home/calum/Downloads/labsuser.pem'
GITHUB_REPO = 'https://github.com/Devorlon/CPDCW1.git'
PYTHON_SCRIPT = 'faceSetup.py'
AMI_ID = 'ami-071226ecf16aa7d96'
INSTANCE_TYPE = 't2.micro'
KEY_NAME = 'vockey'
ANSIBLE_PLAYBOOK = 'ec2Provisioning.yaml'
ANSIBLE_INVENTORY = 'inventory.ini'

ec2 = boto3.client('ec2')

def delete_existing_instances():
    try:
        # Find instances with the FaceSetupInstance tag
        response = ec2.describe_instances(Filters=[
            {
                'Name': 'tag:Name',
                'Values': ['FaceSetupInstance']
            }
        ])
        
        instance_ids = []
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                instance_ids.append(instance['InstanceId'])
        
        if instance_ids:
            print(f'Terminating existing instances: {instance_ids}')
            ec2.terminate_instances(InstanceIds=instance_ids)
            
        return True
    except Exception as e:
        print(f'Error deleting existing instances: {e}')
        return False

def create_ec2_instance():
    try:
        response = ec2.run_instances(
            ImageId=AMI_ID,
            InstanceType=INSTANCE_TYPE,
            KeyName=KEY_NAME,
            SecurityGroupIds=[create_security_group("sgroup-S2131971")],
            MinCount=1,
            MaxCount=1,
            IamInstanceProfile={'Name': 'LabInstanceProfile'},
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [{'Key': 'Name', 'Value': 'FaceSetupInstance'}]
                }
            ]
        )
        instance_id = response['Instances'][0]['InstanceId']
        print(f'Instance {instance_id} is launching...')
        return instance_id
    except Exception as e:
        print(f'Error launching instance: {e}')
    return None

def create_security_group(group_name, description="Allow SSH access"):
    ec2 = boto3.resource('ec2')

    try:
        vpc = list(ec2.vpcs.all())[0]
        
        security_groups = list(ec2.security_groups.filter(Filters=[{'Name': 'group-name', 'Values': [group_name]}]))
        if security_groups:
            print(f"Security group {group_name} already exists with ID {security_groups[0].id}")
            return security_groups[0].id
        
        # Create security group that allows SSH access
        security_group = ec2.create_security_group(
            GroupName=group_name,
            Description=description,
            VpcId=vpc.id
        )
        security_group.authorize_ingress(
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                }
            ]
        )
        print(f"Security group {group_name} created with ID {security_group.id}")
        return security_group.id
    except Exception as e:
        print(f"Error creating security group: {e}")
        return None

def wait_for_instance_running(instance_id):
    try:
        waiter = ec2.get_waiter('instance_running')
        waiter.wait(InstanceIds=[instance_id])
        instance = ec2.describe_instances(InstanceIds=[instance_id])
        public_dns = instance['Reservations'][0]['Instances'][0]['PublicDnsName']
        print(f'Instance is running. Public DNS: {public_dns}')
        return public_dns
    except Exception as e:
        print(f'Error waiting for instance: {e}')
        return None

def generate_ansible_inventory(public_dns):
    # Writes inventory file using paramaritised variables
    inventory_content = f"""
        [face_setup]
        {public_dns} ansible_user=ec2-user ansible_ssh_private_key_file={KEY_PATH}
        
        [face_setup:vars]
        ansible_python_interpreter=/usr/bin/python3
        ansible_ssh_common_args='-o StrictHostKeyChecking=no'
        github_repo={GITHUB_REPO}
    """
    
    with open(ANSIBLE_INVENTORY, 'w') as f:
        f.write(inventory_content)
    print(f"Generated Ansible inventory at {ANSIBLE_INVENTORY}")

def run_ansible_playbook():
    try:
        cmd = [
            'ansible-playbook',
            '-i', ANSIBLE_INVENTORY,
            ANSIBLE_PLAYBOOK
        ]
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # Write the output to the terminal
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())
        
        # Check for errors
        stderr = process.communicate()[1]
        if process.returncode != 0:
            print(f"Ansible playbook failed with error:\n{stderr}")
            return False
        
        print("Ansible playbook executed successfully")
        return True
        
    except Exception as e:
        print(f"Error executing Ansible playbook: {e}")
        return False

def main():
    delete_existing_instances()

    instance_id = create_ec2_instance()

    public_dns = wait_for_instance_running(instance_id)

    time.sleep(30)  # Wait for SSH to become available
    
    # Generate dynamic inventory and run Ansible
    generate_ansible_inventory(public_dns)
    if not run_ansible_playbook():
        print("Failed to provision instance with Ansible")

    # Output SSH command
    print(f"\nTo connect to the instance via SSH, use:")
    print(f"ssh -i {KEY_PATH} ec2-user@{public_dns}")

if __name__ == '__main__':
    main()