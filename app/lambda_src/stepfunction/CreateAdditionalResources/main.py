# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import json
import logging
import traceback
from helper import (
    create_account_alias,
    create_account_tags
)
from account_creation_helper import assume_role_arn

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


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
        payload = event.get('Payload')
        LOGGER.info("Getting Account Id and Name")
        account_number = payload['Account']['Outputs']['AccountId']
        account_name = payload['AccountInfo']['AccountName']

        if not account_name:
            account_name = payload['Account']['Outputs']['ProvisionedProductName']

        assumed_creds = assume_role_arn(
            role_arn=f"arn:aws:iam::{account_number}:role/{os.getenv('ASSUMED_ROLE_NAME')}"
        )

        # Create account alias
        create_account_alias(
            creds=assumed_creds,
            alias=account_name.lower()
        )

        # Create tags within AWS Organizations on AWS Account
        prov_prod_id = payload['Account']['Outputs']['ProvisionedProductId']

        tags = [{
            'Key': 'SCProvisionedProductId',
            'Value': prov_prod_id
        }]

        tags.extend(payload['AccountInfo'].get('AccountTags', []))
        LOGGER.info('Adding account tags: %s', tags)
        create_account_tags(
            account_id=account_number,
            tags=tags
        )

        return payload

    except Exception as e:
        LOGGER.error(traceback.format_exc())
        raise TypeError(str(e)) from e
