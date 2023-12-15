# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import os
from helper import (
    decommission_process_running, 
    pipeline_running
)

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


def lambda_handler(event, context):
    """This function will

    Args:
        event (dict): Event information passed in by the AWS Step Functions
        context (object): Lambda Function context information

    Returns:
        dict: Payload values that will be passed to the next step in the Step Function
    """
    print(json.dumps(event))
    payload = {}

    try:
        # If the Payload key is found this indicates that this isn't the first attempt
        #  and there may be a concurrent Account Factory job running
        if event.get('Payload'):
            account_info = event['Payload']['AccountInfo']
        else:
            account_info = event['AccountInfo']

        payload['CheckForRunningProcesses'] = {}

        # Check to make sure that the decommissioning codebuild process is not running
        project_name = os.getenv("ACCOUNT_DECOMMISSION_PROJECT_NAME")
        if project_name and decommission_process_running(project_name=project_name):
            LOGGER.info('Decommissioning process is running, sending signal to wait...')
            payload['CheckForRunningProcesses']['CodeBuild'] = project_name

        # Check to make sure that the LZA CodePipeline process is not running
        pipeline_name = os.getenv("LZA_PIPELINE_NAME")
        if pipeline_name and pipeline_running(pipeline_name=pipeline_name):
            LOGGER.info('There are other executions in progress, sending signal to wait...')
            payload['CheckForRunningProcesses']['CodePipeline'] = pipeline_name

        # Add the AccountInfo to the paylaod
        payload['AccountInfo'] = account_info
        payload['ForceUpdate'] = str(account_info.get('ForceUpdate', 'false'))
        
        LOGGER.info(f"Payload: {payload}")
        return payload

    except Exception as e:
        LOGGER.exception(e)
        raise TypeError(str(e)) from e
