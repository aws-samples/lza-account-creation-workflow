# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import logging
import botocore
import boto3
from account_creation_helper import assume_role_arn

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


def is_config_logging_configured(account_id: str, log_acct_role_name: str, log_account_name: str):
    """
    Checks if AWS Config is writing logs to the log archive account.

    Validates that AWS Config logs for the given account are being
    written to the designated log archive account and S3 bucket.

    Args:
        account_id (str): ID of the account to check
        log_acct_role_name (str): Role name in log archive account
        log_account_name (str): Name of log archive account

    Returns:
        dict: Status of the log validation check
    """
    LOGGER.info(
        f"Beginning AWS Config log validation for account {account_id}")
    org_client = boto3.client('organizations')
    response = org_client.describe_organization()
    org_id = response['Organization']['Id']

    # Check to see if the ssm parameter exists if not look at the accounts in organizations
    log_acct_param_key = os.getenv('LOG_ARCHIVE_ACCOUNT_SSM')
    log_account_id = get_ssm_parameter(
        parameter_key=log_acct_param_key) or get_account_id_from_name(log_account_name)
    LOGGER.info(
        f"found_log_account: {log_account_id}")

    # Construct variables for checking config log bucket
    log_bucket = f"aws-controltower-logs-{log_account_id}-{os.getenv('AWS_REGION')}"
    log_key = f"{org_id}/AWSLogs/{account_id}/Config/ConfigWritabilityCheckFile"

    LOGGER.info(f"S3 bucket: {log_bucket}")
    assumed_creds = assume_role_arn(
        role_arn=f"arn:aws:iam::{log_account_id}:role{log_acct_role_name}"
    )

    s3_args = {"service_name": "s3"}
    s3_args.update(assumed_creds)
    s3_resource = boto3.resource(**s3_args)

    try:
        s3_resource.Object(log_bucket, log_key).load()

    except botocore.exceptions.ClientError as err:
        if err.response['Error']['Code'] == "404":
            # The object does not exist.
            raise Exception(
                f"The S3 object {log_key} cannot be found in bucket {log_bucket}") from err

        # Something else has gone wrong.
        raise Exception(
            f"Error checking S3 for {log_key} in bucket {log_bucket} :: {err}") from err

    validation_msg = f"Validated AWS Config logs for {account_id}"

    return {
        "Service": "ConfigLogValidation",
        "Status": "Succeeded",
        "Message": validation_msg
    }


def get_ssm_parameter(parameter_key: str):
    """  
    Get SSM Parameter Value

    Args:
        parameter_key (str): SSM Parameter Key to get value for

    Return:
        str: Parameter Value
    """
    ssm_client = boto3.client('ssm')
    response = ssm_client.get_parameters(
        Names=[parameter_key],
    )
    return next((x['Value'] for x in response['Parameters'] if x['Name'] == parameter_key), None)


def get_account_id_from_name(account_name: str) -> str:
    """Looks up the account ID from teh passed in account name

    Args:
        account_name (str): Account name in AWS Organizations

    Returns:
        str: Account ID as a string
    """
    org_client = boto3.client('organizations')
    list_accounts_paginator = org_client.get_paginator('list_accounts')
    accounts_list = list_accounts_paginator.paginate()
    try:
        account_id = next(accounts_list.search(
            f"Accounts[?Name == `{account_name}`].Id"))
        LOGGER.info('Found account id %s for account name %s',
                    account_id, account_name)
        return account_id
    except StopIteration:
        LOGGER.error(
            'No account found matching the account name of %s', account_name)
