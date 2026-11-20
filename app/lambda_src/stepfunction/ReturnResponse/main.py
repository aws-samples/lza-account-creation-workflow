# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import json
import logging

import boto3
from botocore.exceptions import ClientError

from helper import send_sns_message

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)

SNS_CLIENT = boto3.client('sns')


class StepFunctionTaskFailureException(Exception):
    """Exception to be raised when a task in the Step Function fails"""


def lambda_handler(event, context):
    """Return final response from the Step Function execution.

    If an error occurred in a previous step, sends an SNS notification
    and raises an exception. Otherwise returns the created AccountId.

    Args:
        event (dict): Event information passed in by the AWS Step Functions
        context (object): Lambda Function context information

    Returns:
        str: The Account ID of the successfully created account.
    """
    LOGGER.debug('Event: %s', json.dumps(event))

    try:
        if event['StageInput'].get('Error'):
            error_cause = json.loads(event['StageInput']['Cause'])
            error_message = error_cause['errorMessage']
            account_info = event['OriginalInput']['AccountInfo']

            send_sns_message(
                error=error_message,
                account_name=account_info['AccountName']
            )
            raise StepFunctionTaskFailureException(
                'A task in the account creation step function failed: ',
                error_message
            )

        payload = event['StageInput']['Payload']['Account']['Outputs']['AccountId']
        return payload

    except StepFunctionTaskFailureException:
        raise
    except ClientError as client_err:
        LOGGER.error(
            "AWS API error in ReturnResponse: %s", client_err.response['Error']['Message']
        )
        raise RuntimeError(str(client_err)) from client_err
    except (KeyError, json.JSONDecodeError) as parse_err:
        LOGGER.error("Error parsing event payload: %s", parse_err)
        raise RuntimeError(str(parse_err)) from parse_err
    except Exception as e:
        LOGGER.exception("Unexpected error in ReturnResponse")
        raise RuntimeError(str(e)) from e
