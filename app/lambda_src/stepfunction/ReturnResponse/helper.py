# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import logging
import boto3

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)

SNS_CLIENT = boto3.client('sns')


def send_sns_message(error: str, account_name='test', topic=os.getenv('SNS_FAILURE_TOPIC')):
    """
    Sends an SNS message upon failure to create an AWS account.

    The function logs the failure message and topic. It constructs
    a subject and publishes the error message to the given SNS topic.

    Args:
        error (str): The error message text
        account_name (str): The account name (default: 'test') 
        topic (str): The SNS topic ARN (default: env var)

    Returns:
        None
    """
    LOGGER.info(f"Sending failure message to topic: {topic}")
    subject = f"Attention !! Failure during creating AWS Account - {account_name}."
    message = error

    response = SNS_CLIENT.publish(
        TopicArn=topic,
        Message=message,
        Subject=subject
    )
    print(response)
