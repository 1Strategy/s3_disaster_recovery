'''
Copyright 2018 1Strategy, LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.
'''

import boto3
import botocore
import json
import logging
import os

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

def get_bucket_tagset(bucket_name, s3 = boto3.resource('s3')):
    tagging = s3.BucketTagging(bucket_name)
    try:
        tagging.load()
        return tagging.tag_set
    except botocore.exceptions.ClientError:
        return None

def tagging_to_dict(tagset):
    result = {}
    if isinstance(tagset, dict):
        result[tagset['Key'].lower()] = str(tagset['Value']).lower()
    elif isinstance(tagset, list):
        for tag in tagset:
            result[tag['Key'].lower()] = str(tag['Value']).lower()
    else:
        return None

    return result

def to_lower(source_dict):
    result = {}
    if source_dict is None or source_dict == {}:
        return result
    for k, v in source_dict.items():
        key = k.lower() if isinstance(k, str) else k
        value = v.lower() if isinstance(v, str) else v
        result[key] = value
    return result

def is_replication_enabled(bucket_name, s3_client=boto3.client('s3')):
    response = None
    try:
        response = s3_client.get_bucket_replication(Bucket=bucket_name)
    except botocore.exceptions.ClientError:
        LOGGER.info("Replication is not configed for bucket {} yet.".format(
            bucket_name
        ))
    if response is None or response['ReplicationConfiguration']['Rules'][0]['Status'] == 'Disabled':
        return False
    else:
        return True

def check_and_enable_versioning(bucket_name, s3 = boto3.resource('s3')):
    bucket_versioning = s3.BucketVersioning(bucket_name)

    LOGGER.info("Current versioning status of {}: {}".format(
        bucket_name, bucket_versioning.status))

    if bucket_versioning.status != 'Enabled':
        bucket_versioning.enable()

    LOGGER.info("Updated versioning status of {}: {}".format(
        bucket_name, bucket_versioning.status))

    return bucket_versioning.status

def publish_to_topic(
        sns_resource,
        sns_topic_arn = os.environ['sns_topic_arn'],
        sns_client=boto3.client(service_name='sns', region_name='us-east-2')):
    sns_client.publish(TargetArn=sns_topic_arn, Message=sns_resource)

def handler(event, context):

    match_tagging = json.loads(os.environ['match_tagging'])
    request_parameters = event['detail']['requestParameters']

    bucket_name = request_parameters['bucketName']
    bucket_tags = ''

    event_name = event['detail']['eventName']
    LOGGER.info('Processing event: "{}" for bucket "{}".'.format(event_name, bucket_name))

    # "DeleteBucketReplication" and "PutBucketTagging" are the two events we are monitoring in the CloudWatch rule.
    if event_name == 'DeleteBucketReplication':
        bucket_tags = get_bucket_tagset(bucket_name)
    if event_name == 'PutBucketTagging':
        bucket_tags = request_parameters['Tagging']['TagSet']['Tag']
    
    if to_lower(match_tagging).items() <= tagging_to_dict(bucket_tags).items():
        if is_replication_enabled(bucket_name):
            LOGGER.info(
                "Cross region replication is already enabled for bucket: {}".format(bucket_name)
                )
        else:
            check_and_enable_versioning(bucket_name)
            publish_to_topic(bucket_name)           # trigger destination bucket creation
            LOGGER.info(
                "Trying to create destination bucket: {}-dr for replication.".format(bucket_name)
                )
    else:
        LOGGER.info(
            "Bucket: {} is not for DR purpose, add proper tags to enable DR.".format(bucket_name)
            )
