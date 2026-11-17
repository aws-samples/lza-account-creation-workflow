# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import os

from botocore.exceptions import ClientError

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
    """Sync Azure Active Directory groups to AWS Identity Center.

    Looks up group IDs in Azure AD, adds them to the SSO application,
    and triggers synchronization to AWS Identity Center.

    Args:
        event (dict): The event payload containing account info
        context (object): Lambda Context runtime methods and attributes

    Returns:
        dict: The updated payload
    """
    LOGGER.debug('Event: %s', json.dumps(event))

    try:
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
        ad_group_names = list(
            x['ActiveDirectoryGroupName'] for x in account_info["ADIntegration"]
        )

        for ad_group_name in ad_group_names:
            try:
                LOGGER.info("Getting Azure Group Id for Group (%s)", ad_group_name)
                group_api.get_group_info_from_name(ad_group_name)
                group_id_mapping[ad_group_name] = group_api.group_id
                LOGGER.info("Group ID: %s", group_api.group_id)
                payload["AD_Group_Mapping"] = group_id_mapping

            except KeyError as group_not_found:
                raise GraphApiRequestException(
                    "The given group was not found in Azure AD: %s" % ad_group_name
                ) from group_not_found

        LOGGER.info("AD Group Id Mappings: %s", group_id_mapping)

        # Add group to AWS Identity Center Azure AD application
        LOGGER.info(
            "Attempting to move group %s into the SSO sync application",
            group_api.group_id,
        )
        try:
            sso_response = group_api.add_group_to_sso(
                graph_api_secret["object_id"], graph_api_secret["app_role_id"]
            )
            LOGGER.info("SSO Add Response status: %s", sso_response.status_code)
            LOGGER.debug("SSO Add Response body: %s", sso_response.json())

        except GraphApiRequestException as graph_api_exception:
            if "Permission being assigned already exists on the object" in str(
                graph_api_exception
            ):
                LOGGER.info("Group already exists in SSO application, skipping")
            else:
                raise

        # Synchronization
        LOGGER.info(
            "Attempting to start synchronization from Azure AD to AWS Identity Center..."
        )
        sync = Synchronizer(api, graph_api_secret["object_id"])
        sync.sync_azure_ad_aws_identity_center()

        LOGGER.info("Payload keys: %s", list(payload.keys()))
        return payload

    except GraphApiRequestException as graph_err:
        LOGGER.error("Graph API error: %s", graph_err)
        raise RuntimeError(str(graph_err)) from graph_err
    except ClientError as client_err:
        LOGGER.error(
            "AWS API error: %s", client_err.response['Error']['Message']
        )
        raise RuntimeError(str(client_err)) from client_err
    except KeyError as key_err:
        LOGGER.error("Missing required key in payload: %s", key_err)
        raise RuntimeError(str(key_err)) from key_err
    except Exception as e:
        LOGGER.exception("Unexpected error in AzureADGroupSync")
        raise RuntimeError(str(e)) from e
