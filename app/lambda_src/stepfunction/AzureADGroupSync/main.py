# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import os
from helpers import get_secret_value
from ms_graph_api import (
    MsGraphApiConnection,
    MsGraphApiGroups,
    Synchronizer,
    GraphApiRequestException
)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


def lambda_handler(event, context):
    """
    Handles Lambda function triggered by AWS Step Functions.

    The function syncs Azure Active Directory groups to AWS Identity 
    Center by looking up group IDs and adding them to the SSO 
    application. It returns the updated payload.

    Args:
        event (dict): The event payload containing account info
        context (object): Lambda Context runtime methods and attributes

    Returns:
        dict: The updated payload
    """
    try:
        LOGGER.info(json.dumps(event))

        payload = event["Payload"]
        account_info = payload["AccountInfo"]

        # Get Graph API information from secrets manager
        graph_api_secret_name = os.getenv("GRAPH_API_SECRET_NAME")
        LOGGER.info("Getting Azure AD connection info")
        graph_api_secret = json.loads(get_secret_value(graph_api_secret_name))

        # Connect to the API
        api = MsGraphApiConnection(
            client_id=graph_api_secret["client_id"],
            tenant_id=graph_api_secret["tenant_id"],
            client_secret=graph_api_secret["secret_value"],
        )
        group_api = MsGraphApiGroups(api)

        # Set the group ID
        LOGGER.info("Looking up Azure Active Directory Group Id")
        group_id_mapping = {}

        # List of dictionaries
        # Ex. [{"PermissionSetName":"CustomerAccountAdmin","ActiveDirectoryGroupName":"platform-admin"}]
        ad_group_names = list(x['ActiveDirectoryGroupName'] for x in account_info["ADIntegration"])

        for ad_group_name in ad_group_names:
            try:
                LOGGER.info("Getting Azure Group Id for Group (%s)", ad_group_name)
                group_api.get_group_info_from_name(ad_group_name)
                group_id_mapping[ad_group_name] = group_api.group_id
                LOGGER.info("Group ID: %s", group_api.group_id)
                payload["AD_Group_Mapping"] = group_id_mapping

            except KeyError as group_not_found:
                raise GraphApiRequestException(
                    f"The given group was not found in Azure AD {account_info['AzureADGroupName']}"
                ) from group_not_found

        LOGGER.info("AD Group Id Mappings %s", group_id_mapping)

        # Add group to AWS Identity Center Azure AD application
        LOGGER.info(
            "Attempting to move the group %s into the SSO sync application",
            group_api.group_id,
        )
        try:
            sso_response = group_api.add_group_to_sso(
                graph_api_secret["object_id"], graph_api_secret["app_role_id"]
            )
            LOGGER.info("SSO Add Response:")
            LOGGER.info(sso_response.json())

        except GraphApiRequestException as graph_api_exception:
            if "Permission being assigned already exists on the object" in str(
                graph_api_exception
            ):
                LOGGER.info("Group already exists in SSO application, skipping")
            else:
                raise graph_api_exception

        # Synchronization
        LOGGER.info(
            "Attempting to start synchronization from Azure AD to AWS Identity Center..."
        )
        sync = Synchronizer(api, graph_api_secret["object_id"])
        sync.sync_azure_ad_aws_identity_center()

        LOGGER.info("Payload: %s", payload)
        return payload

    except Exception as general_exception:
        LOGGER.exception(str(general_exception))
        raise TypeError(str(general_exception)) from general_exception
