# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import json
import logging
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
    """This function will get the AWS Service Catalog / Control Tower Account Deployment status.

    Args:
        event (dict): Event information passed in by the AWS Step Functions
        context (object): Lambda Function context information

    Returns:
        dict: Payload with additional values for Account Status. This will be passed to the next step in the
        Step Function.
    """
    print(json.dumps(event))
    status = []
    validate_resources = {}

    try:
        payload = event.get('Payload')

        # Get account
        account_id = payload['Account']['Outputs']['AccountId']

        # Ensure that the account is the proper OU
        manage_ou = payload['AccountInfo']['ManagedOrganizationalUnit']
        status.append(is_account_exist_in_ou(account_id=account_id, ou_name=manage_ou))

        # Identify what needs to be validated based on OU
        validate_dict = get_services_to_validate()['validate']
        validate_ou = validate_dict['organizationalUnits']
        for _k, _v in validate_ou.items():
            if _k in manage_ou:
                validate_resources.update(_v)

        assumed_creds = assume_role_arn(
            role_arn=f'arn:aws:iam::{account_id}:role/{os.getenv("ASSUMED_VALIDATION_ROLE_NAME")}'
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
        _valid_s3= ValidateS3(assumed_creds, account=account_id)
        for bucket_name in validate_resources.get("s3", {"buckets": []}).get("buckets", []):
            status.append(_valid_s3.s3_bucket_exist(bucket_name=bucket_name))

        # TODO: Validate Config Rules
        for rules in validate_resources.get("config", {"rules": []}).get("rules", []):
            print(rules)

        # Validate AWS Config logs
        # ASSUMED_CONFIG_LOG_ROLE_NAME env var for checking log and config
        # resource_status = is_config_logging_configured(
        #     account_id=account_id,

        #     log_account_name=os.getenv(
        #         'LOG_ARCHIVE_ACCOUNT_NAME', "Log Archive")
        # )
        #
        # if resource_status['Service'] == 'ConfigLogValidation' and resource_status['Status'] == 'Succeeded':
        #     status.append(resource_status)
        #
        # # Validate AWS Tags
        # try:
        #     tag_validator = ValidateAccountTags(
        #         account_id=account_id,
        #         tags=payload['AccountInfo']['AccountTags']
        #     )
        #     status.append(tag_validator.validate())
        #
        # except KeyError as key_error:
        #     raise TypeError('The list of account tags is missing from the payload.')

        # Checking all status to see if validation is still InProgress
        if next((item for item in status if item['Status'] in ('InProgress', 'RUNNING', 'NOT_STARTED')), None):
            payload['ValidationStatus'] = 'InProgress'

        else:
            payload['ValidationStatus'] = 'COMPLETED'

        payload['ValidationInformation'] = status
        return payload

    except Exception as e:
        LOGGER.error(e)
        raise TypeError(str(e)) from e
