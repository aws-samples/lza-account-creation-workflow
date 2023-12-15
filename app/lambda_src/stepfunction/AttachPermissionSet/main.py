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
    LOGGER.info(json.dumps(event))

    try:
        payload = event['Payload']
        account_info = payload['AccountInfo']
        account_id = payload['Account']['Outputs']['AccountId']
        ad_integration = account_info['ADIntegration']
        group_mappings = payload['AD_Group_Mapping']
        
        LOGGER.info(f"AD Group Mappings: {group_mappings}")
        payload['AccountAssignments'] = []

        identity_store_id, instance_arn = get_sso_instance_id_and_arn()
        LOGGER.info('Identity store id: %s', identity_store_id)
        LOGGER.info('Instance ARN: %s', instance_arn)

        for permission_set_name, ad_group_name in ad_integration.items():
            LOGGER.info('Creating account assignment for Permission Set (%s) with AAD Group (%s) in %s', 
                        permission_set_name, ad_group_name, account_id)
            
            group_guid = lookup_group_guid_from_sso(
                group_name=ad_group_name,
                identity_store_id=identity_store_id
            )
            LOGGER.info('Group GUID: %s', group_guid)

            permission_set_arn = get_permission_set_arn(
                permission_set_name=permission_set_name,
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
