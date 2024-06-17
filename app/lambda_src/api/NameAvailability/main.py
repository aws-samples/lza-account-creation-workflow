# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import logging
import json
import boto3

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


def lambda_handler(event, context):
    """
    Handles Lambda function requests and returns responses.

    Args:
        event (dict): The event passed by Lambda
        context (object): Lambda Context runtime methods and attributes

    Returns:
        dict: The API response including statusCode and body
    """
    LOGGER.info(json.dumps(event))

    org_client = boto3.client(service_name="organizations")
    response = ''

    try:
        # Get account name from API Parameter 
        requested_name = event['queryStringParameters'].get('account_name')

        if not requested_name:
            raise Exception("Please specify \"account_name\" as API Parameter.")

        # List all existing accounts
        list_accounts_paginator = org_client.get_paginator('list_accounts')
        accounts_list = list_accounts_paginator.paginate()
        account_id = next(accounts_list.search(f"Accounts[?Name == `{requested_name}`].Id"), "")

        if account_id:
            response_body = account_id
        else:
            response_body = None

        # Building response for Api Call
        response = {
            "statusCode": 200,
            "body": json.dumps(response_body),
            "isBase64Encoded": False,
            "headers": {
                "content-type": "application/json"
            }
        }

    except Exception as err:
        LOGGER.exception(err)

        # Building response for Api Call
        response = {
            "statusCode": 404,
            "body": f'{"Failure": {err}}',
            "isBase64Encoded": False,
            "headers": {
                "content-type": "application/json"
            }
        }

    finally:
        LOGGER.info(response)
        return response
