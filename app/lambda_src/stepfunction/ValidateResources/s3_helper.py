# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import logging
import boto3

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


class ValidateS3:
    """Class to validate S3
    """
    creds = {}

    def __init__(self, assumed_creds: dict, account: str, region: str = os.environ['AWS_DEFAULT_REGION']):
        self.account = account
        self.region = region
        self.creds = assumed_creds
        s3_args = {"service_name": "s3"}
        s3_args.update(self.creds)
        self.s3_client = boto3.client(**s3_args)

    def s3_bucket_exist(self, bucket_name: str):
        # update bucket name to reflect account name and region
        bucket_name.replace("{{ account }}", self.account)
        bucket_name.replace("{{ region }}", self.region)

        LOGGER.info(f"Checking if S3 Bucket ({bucket_name}) exists.")
        _results = self.s3_client.list_buckets()['Buckets']
        _bucket = next((item for item in _results if item['Name'] == bucket_name), None)

        if not _bucket:
            status = "Failed"
            validation_msg = f"S3 Bucket {bucket_name} does NOT exist in the newly created Account"
        else:
            status = "Passed"
            validation_msg = f"S3 Bucket {bucket_name} exists"

        return {
            "Service": f"S3BucketValidation_{bucket_name}",
            "Status": status,
            "Message": validation_msg
        }
