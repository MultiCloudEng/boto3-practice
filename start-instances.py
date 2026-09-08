import boto3
from botocore.exceptions import ClientError

ec2 = boto3.client('ec2')

instance_id = 'i-068b8900700a95f42'

try:
    response = ec2.start_instances(InstanceIds=[instance_id])
    print("Starting instance:", instance_id)
    print(response['StartingInstances'][0]['CurrentState']['Name'])
except ClientError as e:
    print("Error: could not start instance.")
    print("Reason:", e)
