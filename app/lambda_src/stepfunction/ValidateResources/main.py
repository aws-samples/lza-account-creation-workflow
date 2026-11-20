# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import json
import logging

from botocore.exceptions import ClientError

from organizations_helper import is_account_exist_in_ou
from iam_helper import ValidateIam
from ssm_helper import ValidateSsm
from s3_helper import ValidateS3
from helper import get_services_to_validate
from account_creation_helper import assume_role_arn

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


def lambda_handler(event, context):
    """Validate that AWS resources were created correctly in the new account.

    Args:
        event (dict): Event information passed in by the AWS Step Functions.
        context (object): Lambda Function context information.

    Returns:
        dict: Payload with validation status and information.
    """
    LOGGER.debug('Event: %s', json.dumps(event))
    status = []
    validate_resources = {}

    try:
        payload = event.get('Payload')

        # Get account
        account_id = payload['Account']['Outputs']['AccountId']

        # Ensure that the account is in the proper OU
        manage_ou = payload['AccountInfo']['ManagedOrganizationalUnit']
        status.append(is_account_exist_in_ou(account_id=account_id, ou_name=manage_ou))

        # Identify what needs to be validated based on OU
        validate_dict = get_services_to_validate()['validate']
        validate_ou = validate_dict['organizationalUnits']
        for _k, _v in validate_ou.items():
            if _k in manage_ou:
                validate_resources.update(_v)

        assumed_creds = assume_role_arn(
            role_arn='arn:aws:iam::%s:role/%s' % (account_id, os.getenv("ASSUMED_VALIDATION_ROLE_NAME"))
        )

        # Validate IAM Roles
        _valid_iam = ValidateIam(assumed_creds)
        for roles in validate_resources.get("iam", {"roles": []}).get("roles", []):
            status.append(_valid_iam.iam_role_exist(role_name=roles))

        # Validate SSM Parameters
        _valid_ssm = ValidateSsm(assumed_creds)
        for parameter in validate_resources.get("ssm", {"parameters": []}).get("parameters", []):
            status.append(_valid_ssm.ssm_parameter_exist(parameter_name=parameter))

        # Validate S3 Bucket
        _valid_s3 = ValidateS3(assumed_creds, account=account_id)
        for bucket_name in validate_resources.get("s3", {"buckets": []}).get("buckets", []):
            status.append(_valid_s3.s3_bucket_exist(bucket_name=bucket_name))

        # TODO: Validate Config Rules
        for rules in validate_resources.get("config", {"rules": []}).get("rules", []):
            LOGGER.debug("Config rule to validate: %s", rules)

        # Checking all status to see if validation is still InProgress
        if next((item for item in status if item['Status'] in ('InProgress', 'RUNNING', 'NOT_STARTED')), None):
            payload['ValidationStatus'] = 'InProgress'
        else:
            payload['ValidationStatus'] = 'COMPLETED'

        payload['ValidationInformation'] = status
        return payload

    except ClientError as client_err:
        LOGGER.error(
            "AWS API error during resource validation: %s",
            client_err.response['Error']['Message']
        )
        raise RuntimeError(str(client_err)) from client_err
    except KeyError as key_err:
        LOGGER.error("Missing required key in payload: %s", key_err)
        raise RuntimeError(str(key_err)) from key_err
    except Exception as e:
        LOGGER.exception("Unexpected error in ValidateResources")
        raise RuntimeError(str(e)) from e
