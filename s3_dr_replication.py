'''
Copyright 2018 Jing Liang

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

def enable_replication(
        bucket_name,
        replication_role,
        dest_region,
        boto_s3_client=boto3.client('s3')):
    response = None
    try:
        response = boto_s3_client.get_bucket_replication(Bucket=bucket_name)
    except botocore.exceptions.ClientError:
        LOGGER.info("Replication not configed for bucket {} yet.".format(
            bucket_name
        ))
    if response is None or response['ReplicationConfiguration']['Rules'][0]['Status'] == 'Disabled':
        boto_s3_client.put_bucket_replication(
            Bucket=bucket_name,
            ReplicationConfiguration={
                'Role': replication_role,
                'Rules': [
                    {
                        'Prefix': '',
                        'Status': 'Enabled',
                        'Destination': {
                            'Bucket': "arn:aws:s3:::" + bucket_name + '-dr',
                            'StorageClass': 'STANDARD'
                        }
                    },
                ]
            }
        )
        LOGGER.info(
            'Cross Region Replication is enabled for bucket {}.'.format(
                bucket_name
            ))
    else:
        LOGGER.warning(
            'Cross Region Replication was already enabled for bucket {}.'.format(
                bucket_name
            ))

def handler(event, context):
    bucket_name = event['Records'][0]['Sns']['Message']
    replication_role = os.environ['replication_role_arn']
    dest_region = os.environ['dest_region']

    enable_replication(bucket_name, replication_role, dest_region)
