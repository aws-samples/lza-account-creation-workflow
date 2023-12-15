# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import json
import logging
import boto3
from helper import send_sns_message

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)

SNS_CLIENT = boto3.client('sns')


class StepFunctionTaskFailureException(Exception):
    """Exception to be raised when a task in the Step Function fails"""


def lambda_handler(event, context):
    """This function will get the AWS Service Catalog / Control Tower Account Deployment status.

    Args:
        event (dict): Event information passed in by the AWS Step Functions
        context (object): Lambda Function context information

    Returns:
        dict: Payload with additional values for Account Status. This will be passed to the next step in the
        Step Function.
    """
    print(json.dumps(event))

    try:
        if event['StageInput'].get('Error'):
            payload = {"errorMessage": json.loads(event['StageInput']['Cause'])[
                'errorMessage']}
            account_info = event['OriginalInput']['AccountInfo']
            send_sns_message(error=json.loads(event['StageInput']['Cause'])[
                             'errorMessage'], account_name=account_info['AccountName'])
            raise StepFunctionTaskFailureException(
                'A task in the account creation step function failed: ', payload.get('errorMessage'))

        else:
            payload = event['StageInput']['Payload']['Account']['Outputs']['AccountId']

        return payload

    except Exception as e:
        LOGGER.error(e)
        raise TypeError(str(e)) from e
