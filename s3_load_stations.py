import boto3
import json

s3 = boto3.resource('s3')

content_object = s3.Object('epa-weather-history', 'emr-data/stations.json')
file_content = content_object.get()['Body'].read().decode('utf-8')
json_content = json.loads(file_content)
print(json_content)
