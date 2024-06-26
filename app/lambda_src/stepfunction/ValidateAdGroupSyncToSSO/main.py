# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import os
from identity_center_helper import (
    lookup_group_guid_from_sso,
    get_sso_instance_id_and_arn,
    ObjectNotFoundInIdentityCenter
)

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)

WAIT_LIMIT = int(os.getenv('WAIT_LIMIT_IN_MINUTES', '15'))


class ExceededWaitTimeLimit(Exception):
    """Custom exception for when the wait time limit has been exceeded"""


def lambda_handler(event, context):
    """
    Validates Active Directory group sync to AWS SSO.

    The function checks if AD groups from the payload have 
    synced to AWS SSO. It retries if not found, incrementing 
    a wait count. Returns the updated payload.

    Args:
        event (dict): Event payload containing account info
        context (object): Lambda Context runtime methods  

    Returns:
        dict: Updated payload with sync status
    """
    LOGGER.info(json.dumps(event))
    try:
        payload = event['Payload']

        # List of dictionaries
        # Ex. [{"PermissionSetName":"CustomerAccountAdmin","ActiveDirectoryGroupName":"platform-admin"}]
        group_names = list(x['ActiveDirectoryGroupName'] for x in payload['AccountInfo']["ADIntegration"])

        identity_store_id, _ = get_sso_instance_id_and_arn()
        LOGGER.info('Identity store id: %s', identity_store_id)

        if not payload.get('AzureAD'):
            payload['AzureAD'] = {}
            payload['AzureAD']['WaitCount'] = 0

        try:
            for group_name in group_names:
                LOGGER.info('Checking Group Sync for GroupName: %s', group_name)
                lookup_group_guid_from_sso(
                    group_name=group_name,
                    identity_store_id=identity_store_id
                )
                payload['AzureAD']['WaitForAdSync'] = False

        except ObjectNotFoundInIdentityCenter:
            payload['AzureAD']['WaitForAdSync'] = True
            payload['AzureAD']['WaitCount'] = int(
                payload['AzureAD']['WaitCount']) + 1

            if payload['AzureAD']['WaitCount'] > WAIT_LIMIT:
                raise ExceededWaitTimeLimit(
                    'Wait time limit of {} minutes exceeded'.format(WAIT_LIMIT)
                )

            LOGGER.info('Group %s not found in Identity Center', group_name)
            LOGGER.info('Waiting for group to be synched')

        return payload
    except Exception as e:
        LOGGER.exception(e)
        raise TypeError(str(e)) from e
