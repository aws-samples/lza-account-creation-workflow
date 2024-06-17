# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import json
import logging
from identity_center_helper import (
    create_account_assignment_for_group,
    lookup_group_guid_from_sso,
    get_sso_instance_id_and_arn,
    get_permission_set_arn
)

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


def lambda_handler(event, context):
    """
    Handles a Lambda function that assigns permissions to AWS accounts.

    The function is passed an event containing payload data and 
    assigns permissions to the account based on the AD integration 
    configuration in the payload.

    Args:
        event (dict): The event payload containing account info
        context (object): Lambda Context runtime methods and attributes

    Returns:
        dict: The updated payload with account assignments appended
    """
    LOGGER.info(json.dumps(event))

    try:
        payload = event['Payload']
        account_info = payload['AccountInfo']
        account_id = payload['Account']['Outputs']['AccountId']
        ad_integration = account_info['ADIntegration']

        payload['AccountAssignments'] = []

        identity_store_id, instance_arn = get_sso_instance_id_and_arn()
        LOGGER.info('Identity store id: %s', identity_store_id)
        LOGGER.info('Instance ARN: %s', instance_arn)

        for item in ad_integration:
            LOGGER.info('Creating account assignment for Permission Set (%s) with AAD Group (%s) in %s',
                        item['PermissionSetName'], item['ActiveDirectoryGroupName'], account_id)

            group_guid = lookup_group_guid_from_sso(
                group_name=item['ActiveDirectoryGroupName'],
                identity_store_id=identity_store_id
            )
            LOGGER.info('Group GUID: %s', group_guid)

            permission_set_arn = get_permission_set_arn(
                permission_set_name=item['PermissionSetName'],
                instance_arn=instance_arn
            )
            LOGGER.info('Permission set ARN: %s', permission_set_arn)

            response = create_account_assignment_for_group(
                account_id=account_id,
                permission_set_arn=permission_set_arn,
                group_guid=group_guid,
                instance_arn=instance_arn
            )
            payload['AccountAssignments'].append(response['AccountAssignmentCreationStatus'])

        LOGGER.info(response)
        return payload

    except Exception as e:
        LOGGER.exception(e)
        raise TypeError(str(e)) from e
