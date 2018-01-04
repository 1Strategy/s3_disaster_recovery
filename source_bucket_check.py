import boto3
import logging
import json
import botocore

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)
logging.basicConfig(level=logging.INFO)

def check_and_enable_bucket_versioning(bucket_name, s3_resource):
    bucket_versioning = s3_resource.BucketVersioning(bucket_name)
    LOGGER.info('Current versioning status of bucket {} is: {}'.format(
        bucket_name, bucket_versioning.status))

    bucket_versioning.load()
    if bucket_versioning.status is None or bucket_versioning.status == 'Suspended':
        bucket_versioning.enable()
        LOGGER.info('Versioning of bucket {} is enabled'.format(bucket_name))
    else:
        LOGGER.info('Versioning of bucket {} is enabled'.format(bucket_name))

def handler(bucket_name):
    dr_tag = {'Value':'true', 'Key':'DR'}
    source_region = 'us-west-2'
    destination_region = 'us-east-2'
    # request_parameters = event['detail']['requestParameters']
    # source_bucket_name = request_parameters['bucketName']
    source_bucket_name = bucket_name
    destination_bucket_name = source_bucket_name + '-DR'
    s3_resource_source = boto3.resource('s3', region_name=source_region)
    s3_resource_destination = boto3.resource('s3', region_name=destination_region)

    # Check and enable source bucket versioning
    s3_source_bucket_tagging = s3_resource_source.BucketTagging(source_bucket_name)
    if dr_tag in s3_source_bucket_tagging.tag_set:
        LOGGER.info('CRR will be enabled for bucket: {}'.format(source_bucket_name))
        check_and_enable_bucket_versioning(source_bucket_name, s3_resource_source)
    else:
        LOGGER.info('Bucket {} is NOT in the scope of disaster recovery'.format(source_bucket_name))
        return

    # Init destination bucket
    try:
        s3_resource_destination.create_bucket(
            Bucket=destination_bucket_name,
            CreateBucketConfiguration={
                'LocationConstraint': destination_region
            }
        )
        LOGGER.info('Destination bucket {} is created successfully in region {}'.format(
            destination_bucket_name, destination_region))

    except botocore.exceptions.ClientError:
        LOGGER.info('Destination bucket {} already exists in region {}.'.format(destination_bucket_name, destination_region))

    check_and_enable_bucket_versioning(destination_bucket_name, s3_resource_destination)

    # Init cross-region-replication on source bucket
    s3_client_source = boto3.client('s3',region_name='us-west-2')
    s3_client_source.put_bucket_replication(
        Bucket=source_bucket_name,
        ReplicationConfiguration={
            'Role': 'arn:aws:iam::842337631775:role/cambia-dr-role',
            'Rules': [
                {
                    'ID': 'replication_rule_kms_disabled',
                    'Prefix': '',
                    'Status': 'Enabled',
                    'Destination': {
                        'Bucket': 'arn:aws:s3:::' + destination_bucket_name
                    }
                }
            ]
        }
    )

handler('1a-test01')
