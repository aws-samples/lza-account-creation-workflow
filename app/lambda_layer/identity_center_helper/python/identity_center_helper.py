# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import logging
import boto3

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


class ObjectNotFoundInIdentityCenter(Exception):
    """Custom exception for when an object is not found in Identity Center."""


def create_account_assignment_for_group(account_id: str, permission_set_arn: str, group_guid: str,
                                        instance_arn: str, test_client: boto3.client = None) -> dict:
    """Link group to permission set in AWS SSO for the account.

    Args:
        account_id (str): AWS Account ID
        permission_set_name (str): Identity and Access Management permission set name
        group_name (str): Identity and Access Management group name

    Returns:
        dict: boto3 response
    """
    client = boto3.client('sso-admin') if not test_client else test_client

    LOGGER.info('Creating account assignment for %s in %s', group_guid, account_id)

    response = client.create_account_assignment(
        InstanceArn=instance_arn,
        TargetId=account_id,
        TargetType='AWS_ACCOUNT',
        PermissionSetArn=permission_set_arn,
        PrincipalType='GROUP',
        PrincipalId=group_guid
    )
    LOGGER.info(response)
    return response


def lookup_group_guid_from_sso(group_name: str, identity_store_id: str, test_client: boto3.client = None) -> str:
    """Lookup the group GUID from AWS SSO.

    Args:
        group_name (str): Identity and Access Management group name

    Returns:
        str: GUID of the group
    """
    client = boto3.client('identitystore') if not test_client else test_client
    paginator = client.get_paginator('list_groups')
    LOGGER.info('Looking up group %s in AWS SSO', group_name)
    for page in paginator.paginate(IdentityStoreId=identity_store_id):
        for group in page['Groups']:
            LOGGER.debug('Found group %s', group['DisplayName'])
            if group['DisplayName'].lower() == group_name.lower():
                LOGGER.info('Match found, returning guid: %s',
                            group['GroupId'])
                return group['GroupId']
    raise ObjectNotFoundInIdentityCenter(
        f'Group {group_name} not found in Identity Center')


def get_sso_instance_id_and_arn(test_client: boto3.client = None) -> tuple[str, str]:
    """Get the AWS SSO instance ARN.

    Returns:
        str: AWS SSO instance store id and ARN
    """
    client = boto3.client('sso-admin') if not test_client else test_client
    response = client.list_instances()
    try:
        return response['Instances'][0]['IdentityStoreId'], response['Instances'][0]['InstanceArn']
    except (IndexError, KeyError) as not_found_error:
        raise ObjectNotFoundInIdentityCenter(
            'No AWS SSO instance found') from not_found_error


def get_permission_set_arn(permission_set_name: str, instance_arn: str, test_client: boto3.client = None) -> str:
    """Get the AWS SSO permission set ARN.

    Returns:
        str: AWS SSO permission set ARN
    """
    client = boto3.client('sso-admin') if not test_client else test_client
    paginator = client.get_paginator('list_permission_sets')
    permission_set_arns_list = []
    for page in paginator.paginate(InstanceArn=instance_arn):
        permission_set_arns_list.extend(page['PermissionSets'])

    for permission_set in permission_set_arns_list:
        permission_set = client.describe_permission_set(
            InstanceArn=instance_arn,
            PermissionSetArn=permission_set
        )['PermissionSet']

        if permission_set['Name'] == permission_set_name:
            return permission_set['PermissionSetArn']

    raise ObjectNotFoundInIdentityCenter(
        f'Permission set {permission_set_name} not found in Identity Center')
