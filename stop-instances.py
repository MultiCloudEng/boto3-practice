import boto3
from botocore.exceptions import ClientError

ec2 = boto3.client('ec2')

instance_id = 'i-068b8900700a95f42'

try:
   response = ec2.stop_instances(InstanceIds=[instance_id])
   print('Stopping instance:', instance_id)
   print(response['StoppingInstances'][0]['CurrentState']['Name'])
except ClientError as e:
   print("Error could not stop instance.")
   print("Reason:", e)
