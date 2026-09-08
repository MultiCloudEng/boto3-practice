import boto3

ec2 = boto3.client('ec2')

response = ec2.describe_instances()

for reservation in response['Reservations']:
    for instance in reservation['Instances']:
        state = instance['State']['Name']
        if state == 'running':
           print(instance['InstanceId']," is ruuning")
        else:
           print(instance['InstanceId'], "is not running, state: ",state) 
