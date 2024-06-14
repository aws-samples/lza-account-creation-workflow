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
    """
    Creates SSM Parameters for the AWS Account Tags

    Args:
        client (boto3.client): boto3 client
        tags (list): list of AWS Account Tags
    
    Returns:
        None
    """
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
    """
    Deletes AWS Systems Manager (SSM) parameters for the given list of tags.

    Args:
        client (boto3.client): A Boto3 client for the AWS Systems Manager service.
        tags (list): A list of tag names for which the corresponding SSM parameters should be deleted.

    Returns:
        None
    """    
    for tag in tags:
        LOGGER.info(f"Deleting SSM Parameter /account/tags/{tag}")
        client.delete_parameter(
            Name=f"/account/tags/{tag}"
        )
