# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import os

from botocore.exceptions import ClientError
from account_creation_helper import (
    decommission_process_running,
    pipeline_running
)

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


def lambda_handler(event, context):
    """
    Checks for running processes as part of an AWS Step Functions workflow.

    The function extracts account info from the event and checks
    for running CodeBuild and CodePipeline processes by name. It
    returns a payload containing the check results.

    Args:
        event (dict): The event payload from Step Functions
        context (object): Lambda Context runtime methods and attributes

    Returns:
        dict: Payload with check results to pass to next step
    """
    LOGGER.info("CheckForRunningProcesses invoked")
    LOGGER.debug("Event: %s", json.dumps(event))
    payload = {}

    try:
        # If the Payload key is found this indicates that this isn't the first attempt
        # and there may be a concurrent Account Factory job running
        if event.get('Payload'):
            account_info = event['Payload']['AccountInfo']
        else:
            account_info = event['AccountInfo']

        payload['CheckForRunningProcesses'] = {}

        # Check to make sure that the decommissioning codebuild process is not running
        project_name = os.getenv("ACCOUNT_DECOMMISSION_PROJECT_NAME")
        if project_name and decommission_process_running(project_name=project_name):
            LOGGER.info(
                'Decommissioning process is running, sending signal to wait...'
            )
            payload['CheckForRunningProcesses']['CodeBuild'] = project_name

        # Check to make sure that the LZA CodePipeline process is not running
        pipeline_name = os.getenv("LZA_PIPELINE_NAME")
        if pipeline_name and pipeline_running(pipeline_name=pipeline_name):
            LOGGER.info(
                'There are other executions in progress, sending signal to wait...'
            )
            payload['CheckForRunningProcesses']['CodePipeline'] = pipeline_name

        # Add the AccountInfo to the payload
        payload['AccountInfo'] = account_info
        payload['ForceUpdate'] = str(account_info.get('ForceUpdate', 'false'))

        LOGGER.info("Payload keys: %s", list(payload.keys()))
        return payload

    except KeyError as err:
        LOGGER.error("Missing required key in event: %s", err)
        raise RuntimeError(f"Missing required key in event: {err}") from err
    except ClientError as err:
        LOGGER.error("AWS API error: %s", err)
        raise RuntimeError(f"AWS API error: {err}") from err
    except Exception as err:
        LOGGER.exception("Unexpected error in CheckForRunningProcesses")
        raise RuntimeError(str(err)) from err
