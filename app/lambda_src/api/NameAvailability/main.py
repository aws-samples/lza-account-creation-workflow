# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import re
import logging
import json

import boto3
from botocore.exceptions import ClientError

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)

ORG_CLIENT = boto3.client("organizations")

ACCOUNT_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-]{1,48}[a-zA-Z0-9]$')


def lambda_handler(event, context):
    """
    Checks if an AWS account name is already in use in Organizations.

    Args:
        event (dict): The event passed by API Gateway
        context (object): Lambda Context runtime methods and attributes

    Returns:
        dict: API response with account ID if name exists, null if available
    """
    LOGGER.info("NameAvailability invoked")

    try:
        query_params = event.get('queryStringParameters') or {}
        requested_name = query_params.get('account_name')

        if not requested_name:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": {
                        "code": "MISSING_PARAMETER",
                        "message": "account_name query parameter is required",
                        "field": "account_name"
                    }
                }),
                "isBase64Encoded": False,
                "headers": {"content-type": "application/json"}
            }

        if not ACCOUNT_NAME_PATTERN.match(requested_name):
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "account_name must be 3-50 alphanumeric characters and hyphens",
                        "field": "account_name"
                    }
                }),
                "isBase64Encoded": False,
                "headers": {"content-type": "application/json"}
            }

        # List all existing accounts and check for name match
        list_accounts_paginator = ORG_CLIENT.get_paginator('list_accounts')
        accounts_list = list_accounts_paginator.paginate()
        account_id = next(
            accounts_list.search(f"Accounts[?Name == `{requested_name}`].Id"),
            ""
        )

        response_body = account_id if account_id else None

        return {
            "statusCode": 200,
            "body": json.dumps(response_body),
            "isBase64Encoded": False,
            "headers": {"content-type": "application/json"}
        }

    except ClientError as err:
        LOGGER.error("AWS API error in NameAvailability: %s", err)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": {
                    "code": "AWS_ERROR",
                    "message": "Internal service error"
                }
            }),
            "isBase64Encoded": False,
            "headers": {"content-type": "application/json"}
        }
    except Exception as err:
        LOGGER.exception("Unexpected error in NameAvailability")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Internal service error"
                }
            }),
            "isBase64Encoded": False,
            "headers": {"content-type": "application/json"}
        }
