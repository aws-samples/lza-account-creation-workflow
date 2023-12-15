# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import logging
import boto3

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


def create_account_alias(creds: dict, alias: str):
    """Creates an account alias

    Args:
        creds (str): Assumed Role Credentials
        alias (str): Account Alias Name

    Returns:
        None
    """
    iam_args = {"service_name": "iam"}
    iam_args.update(creds)
    iam_client = boto3.client(**iam_args)

    LOGGER.info(f"Searching for Account Alias:{alias}")
    acc_alias = iam_client.get_paginator('list_account_aliases')
    for _acc_alias in acc_alias.paginate():
        alias_exists = _acc_alias['AccountAliases']

    if alias not in alias_exists:
        LOGGER.info(f"Creating Account Alias:{alias}")
        try:
            iam_client.create_account_alias(
                AccountAlias=alias
            )
        except iam_client.exceptions.EntityAlreadyExistsException as alias_exists_exception:
            LOGGER.info('Attempted to create alias %s but it already exists: %s',
                        alias, alias_exists_exception)


def create_account_tags(account_id: str, tags: list):
    """Creates tags on AWS Account within AWS Orgnizations

    Args:
        account_id (str): Account ID to add tags too
        tags (list): Tags to add to Account ID

    Returns:
        None
    """
    orgs_client = boto3.client('organizations')
    response = orgs_client.tag_resource(
        ResourceId=account_id,
        Tags=tags
    )
    LOGGER.info('Added account tags')
    LOGGER.debug(response)
