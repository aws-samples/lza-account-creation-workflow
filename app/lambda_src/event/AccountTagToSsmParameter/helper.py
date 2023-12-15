# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import logging
import os
import boto3

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


def create_ssm_parameters(client: boto3.client, tags: list):
    # Generate Docstring
    for tag in tags:
        LOGGER.info(f"Creating SSM Parameter /account/tags/{tag['key']} with value {tag['value']}")
        client.put_parameter(
            Name=f"/account/tags/{tag['key']}",
            Description='This SSM Parameter is set from the AWS Account Tags located in Organizations '
                        'within the Management Account',
            Value=tag['value'],
            Type='String',
            Overwrite=True
        )
        client.add_tags_to_resource(
            ResourceType='Parameter',
            ResourceId=f"/account/tags/{tag['key']}",
            Tags=[
                {
                    'Key': 'CreatedBy',
                    'Value': f"Lambda:{os.environ['AWS_LAMBDA_FUNCTION_NAME']}"
                },
                {
                    'Key': 'AccountCreationComponent',
                    'Value': 'true'
                }
            ]
        )


def delete_ssm_parameters(client: boto3.client, tags: list):
    for tag in tags:
        LOGGER.info(f"Deleting SSM Parameter /account/tags/{tag}")
        client.delete_parameter(
            Name=f"/account/tags/{tag}"
        )
