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

def check_and_enable_versioning(bucket_name, s3 = boto3.resource('s3')):
    bucket_versioning = s3.BucketVersioning(bucket_name)

    LOGGER.info("Current versioning status of {}: {}".format(
        bucket_name, bucket_versioning.status))

    if bucket_versioning.status != 'Enabled':
        bucket_versioning.enable()

    LOGGER.info("Updated versioning status of {}: {}".format(
        bucket_name, bucket_versioning.status))

    return bucket_versioning.status

def create_destination_bucket(source_bucket_name, target_region, log_bucket_name=os.environ['s3_logging_bucket'], boto_s3=boto3.resource('s3')):
    # Create destination bucket
    dest_bucket_name = source_bucket_name + "-dr"
    new_bucket = boto_s3.Bucket(dest_bucket_name)
    if new_bucket.creation_date is None:
        new_bucket = boto_s3.create_bucket(
            Bucket=dest_bucket_name,
            CreateBucketConfiguration={
                'LocationConstraint': target_region
            }
        )
        LOGGER.info('Destination Bucket {} was created successfully in region {}'.format(
            dest_bucket_name, target_region))
    else:
        LOGGER.info('Destination Bucket {} already exists in region {}'.format(
            dest_bucket_name, target_region))

def publish_to_topic(
        sns_resource,
        sns_topic_arn = os.environ['sns_topic_arn'],
        sns_client=boto3.client(service_name='sns', region_name='us-west-2')):
    sns_client.publish(TargetArn=sns_topic_arn, Message=sns_resource)

def handler(event, context):
    source_bucket_name = event['Records'][0]['Sns']['Message']

    create_destination_bucket(source_bucket_name, 'us-east-2')

    dest_bucket_name = source_bucket_name + "-dr"
    if check_and_enable_versioning(dest_bucket_name) == "Enabled":
        # trigger source replication
        publish_to_topic(source_bucket_name)
    else:
        LOGGER.error("Failed to enable versioning for DR destination bucket {}.".format(
            dest_bucket_name
        ))
