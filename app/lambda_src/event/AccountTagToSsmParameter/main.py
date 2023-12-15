# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import os
import boto3
from account_creation_helper import assume_role_arn
from helper import create_ssm_parameters, delete_ssm_parameters


LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


def lambda_handler(event, context):
    ''' 
    This function creates an SSM Parameter in the target account based on Tags attached to the account within 
    AWS Organizations. The SSM Parameters will be prefixed with "/account/tags/".
    '''
    print(json.dumps(event))

    detail = event['detail']
    event_name = detail.get('eventName')
    account_number = detail['requestParameters']['resourceId']

    assumed_creds = assume_role_arn(
        role_arn=f"arn:aws:iam::{account_number}:role/{os.getenv('ASSUMED_ROLE_NAME')}"
    )

    ssm_args = {"service_name": "ssm"}
    ssm_args.update(assumed_creds)
    ssm_client = boto3.client(**ssm_args)

    try:
        if event_name == 'TagResource':
            LOGGER.info("Found TagResource EventName")
            tags = detail['requestParameters']['tags']
            create_ssm_parameters(
                client=ssm_client,
                tags=tags
            )

        elif event_name == 'UntagResource':
            LOGGER.info("Found UntagResource EventName")
            tag_keys = detail['requestParameters']['tagKeys']
            delete_ssm_parameters(
                client=ssm_client,
                tags=tag_keys
            )

        else:
            LOGGER.warning('Could not identify event name (TagResource or UntagResource)')

    except Exception as err:
        LOGGER.error(Exception(err))
