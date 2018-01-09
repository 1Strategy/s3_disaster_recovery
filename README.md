# Amazon S3 Cross-Region Disaster Recovery

"You can’t predict a disaster, but you can be prepared for one!"

Disaster Recovery (DR) is one of most important requirements we hear from our customers.

AWS services are designed with DR considerations in mind. S3, for example achieves 99.999999999% durability and 99.99% availability by redundantly storing data across multiple AZs within a region.

It may be rare for the whole AWS region to go down, but it could cause massive permanent damage if we don't plan for it. And this is when S3 **Cross-Region Replication (CRR)** solution comes into play.

## Solution Overview

This solution is based on CloudWatch, SNS, and Lambda. It uses an Ansible Playbook to automate deployment of the AWS resources. After you deploy this, the Lambda functions will set up [S3 Cross-Region Replication](https://docs.aws.amazon.com/AmazonS3/latest/dev/crr.html) for any S3 bucket tagged with "DR=true". The Lambda functions will be triggered by AWS S3-related CloudWatch Events on bucket creation or tagging.

Here is an overview of how the solution works:

![S3 DR overview diagram](./s3-dr-cloudwatch-design.png)

1. The DR solution will be triggered by two CloudWatch events - `PutBucketTagging` and `DeleteBucketReplication` on the source S3 bucket.

> Note: When you create a bucket with tags, both `CreateBucket` and `PutBucketTagging` events are triggered, so you only need to fire the Lambda function on `PutBucketTagging`.

2. The CloudWatch rule will trigger the `source_bucket_check` Lambda function which enables [S3 versioning](http://docs.aws.amazon.com/AmazonS3/latest/dev/Versioning.html) on the source bucket.

3. After enabling source bucket versioning, the `source_bucket_check` function sends the source bucket name in a JSON message to the `sns_topic_01` SNS topic in the destination region.

4. The Lambda function (called `destination_bucket_check`) which subscribed to topic sns_topic_01 will be triggered, and it will create the destination bucket in the DR region and enable versioning.

5. Function `destination_bucket_check` sends a message to another SNS topic (called sns_topic_02) which is defined in the source region with source bucket name info.

6. The Lambda function (called `enable_replication`) which subscribed to topic `sns_topic_02` will be triggered, and it will enable cross-region replication on the source bucket.

All these AWS resources are deployed using the included Ansible Playbook.

Since S3 Cross-Region Replication only watches the source buckets for new and updated objects, if you need to replicate existing objects, you should use the [S3 sync API](http://docs.aws.amazon.com/cli/latest/reference/s3/sync.html) to sync all existing objects to the destination bucket.

## Environment Setup and Solution Deployment

Here are the steps to get the solution up and running so you can see the result first before we dig into more details.

1. Install and set up below environment on your local machine assuming you are using Linux or MacOS:

* Ansible 2.4.1+
* Python 3.6+
* Boto3 1.4.8+
* Botocore 1.8.1+
* AWS CLI

2. Create an IAM Role with following permissions, and make sure you have the permissions to assume this Role.

* CloudWatch Full Access
* Lambda Full Access
* SNS Full Access
* S3 Full Access

3. Add below trusted entities to the role, so these services can operate on your behalf:

* The identity provider(s) s3.amazonaws.com
* The identity provider(s) events.amazonaws.com
* The identity provider(s) lambda.amazonaws.com

4. Clone [this repository](https://github.com/1Strategy/s3_disaster_recovery) to your local machine.

5. Update the the variables in Ansible playbook `./playbooks/dr_setup_cloudwatch.yml`

```yaml
  vars:
    # Update this with the IAM role you created in step 2 above.
    dr_role_arn: '<IAM role arn>'
    # Update this with your desired source region
    source_region: 'us-west-2'
    # Update this with your desired destination region
    dest_region: 'us-east-2'
    # matching tag for DR enabled bucket in json format.
    # NOTE: please keep the extra space in the beginning.
    match_tagging: ' {"dr": "true"}'
```

6. Run the Ansible playbook

```bash
cd playbooks
ansible-playbook dr_setup_cloudwatch.yml -vvv
```

7. Test the solution by creating a new bucket (e.g dr-test-bucket) with tag "dr: true" in your source region. In a few seconds, the `dr-test-bucket-dr` should be created automatically in the destination region and replication should be set up between the source bucket (dr-test-bucket) and the target bucket (dr-test-bucket-dr). Add some objects to the source bucket and check the destination bucket in a few seconds to make sure they replicated successfully.

Great, now you have the solution up and running on your environment. Let's see how it works in detail in following sections.

## Some key considerations about S3 Cross-Region Replication (CRR)

Before we drill into detail code, let's take a closer look at S3 Cross-Region Replication.

* CRR applies to new and updated objects in the S3 source buckets, any objects stored prior to enabling this feature are not replicated.

* The source and destination buckets must have versioning enabled.

* The replication process also copies any metadata and ACLs (Access Control Lists) associated with the object, however, the bucket level permissions and properties are not replicated

* CRR supports both AES-256 and KMS encryption, but KMS encryption is turned off by default.

* Every S3 bucket has a unique name, so if you’d like to start using your S3 replica, you will need to configure your business applications to use the destination buckets.

* It is difficult to manually enable and manage cross-region replication for hundreds of buckets, so we need a way to automate it.

For more details, please refer to [What Is and Is Not Replicated](http://docs.aws.amazon.com/AmazonS3/latest/dev/crr-what-is-isnot-replicated.html)

## Lambda Functions

The included Lambda functions are written in Python 3 and use boto3 to access AWS APIs. AWS Lambda provides a built-in environment with boto3 installed, but the version may be lower than the latest boto3 release. So if you want to use some of the new features in latest boto3, you'll need to package the latest boto3 with your Lambda function.

For example, at publication time AWS Lambda installs boto3 1.4.7 which doesn't support KMS encrypted Cross-Region Replication, while 1.4.8 does.

How to package a newer version of Boto3:

```
# create a separate directory
$ mkdir s3-dr-replication

# download the latest boto3 into the directory
$ pip3 install boto3 -t ./s3-dr-replication

# copy the lambda function (e.g.s3_dr_replication.py) to the directory
$ cp s3_dr_replication.py ./s3-dr-replication

# create a zip file contains all the files
cd s3-dr-replication
zip -r s3-dr-replication.zip .
cp s3-dr-replication.zip ..
```

## Ansible Playbook

Something to keep in mind for the Ansible playbook:
1. Ansible's AWS support depends on boto3 and AWS CLI

2. Use localhost since we are only using your local machine to send API requests to AWS and all resources will be created on cloud

3. Set gather_facts to true, since the playbook needs access to environment variables set in previous section to get your key id and access key.

4. Use Ansibles `sts\_assume\_role` module to assume the role created above, and use the session_token from the assumed sts role to perform all other tasks.

```yaml
  tasks:
    - name: Assume role
      sts_assume_role:
        region: 'us-west-2'
        role_arn: '{{ dr_role_arn }}'
        role_session_name: "ansible_sandbox"
      register: assumed_role

    - name: Create SNS topics
      sns_topic:
        name: 'topic_1'
        aws_access_key: '{{ assumed_role.sts_creds.access_key }}'
        aws_secret_key: '{{ assumed_role.sts_creds.secret_key }}'
        security_token: '{{ assumed_role.sts_creds.session_token }}'
        ...
```

5. Create the 3 lambda functions, then 2 SNS topics and SNS subscriptions, at last create the CloudWatch event rule.

6. Use the `lambda_policy` module to add policy to each Lambda function to allow SNS and CloudWatch to invoke them.

```yaml
      lambda_policy:
        state: 'present'
        function_name: 'source_bucket_check'
        statement_id: 'unique_id'
        action: lambda:InvokeFunction
        principal: 'events.amazonaws.com'
        source_arn: '{{ arn_of_cloud_watch_rule }}'
        region: '{{ target_region }}'
```

Most of the Ansible modules are idempotent. And use -vvv option to see detailed logs.

## Bucket properties and permissions

Cross-region replication will not take care of the properties e.g. permissions, taggings, lifecycle rules. So you'll need to write your own code to clone all these properties. Boto3 has very good support on all these APIs.

## Conclusion

AWS provides a very good Cross-Region Replication feature for S3, and to make it work in real life scenario, we need some scripting work to enable/disable replication based on tags, set the replication rule with proper encryption options, clone bucket properties and permissions, copy existing objects and automate all of these process.

I hope this post will help you create an automated S3 cross-region DR solution.

As always, feel free to contact us if you'd like help implemented a fully-featured DR solution for your company.