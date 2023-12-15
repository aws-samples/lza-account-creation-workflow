# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import logging
import boto3

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


def decommission_process_running(project_name: str) -> list:
    """Checks to see if the decommission CodeBuild project is running
    Args:
        project_name (str): CodeBuild Project that runs the decommissioning script

    Returns:
        list: Results for all IN_PROGRESS CodeBuilds jobs
    """
    cb_client = boto3.client('codebuild')
    LOGGER.info(f"Looking for processes from CodeBuild Project: {project_name}")
    try:
        _paginator = cb_client.get_paginator('list_builds_for_project')
        _iterator = _paginator.paginate(
            projectName=project_name
        )
        for _iter in _iterator:
            response = cb_client.batch_get_builds(
                ids=_iter['ids']
            )['builds']
            in_progress = list(item for item in response if item.get('buildStatus') == 'IN_PROGRESS')
            LOGGER.debug(f"in_progress: {in_progress}")
            return in_progress

    except Exception as err:
        LOGGER.error(err)


def pipeline_running(pipeline_name: str) -> list:
    """Check if there are other executions of the pipeline currently running
    Args:
        pipeline_name (str): CodePipeline Name

    Returns:
        list: Results for all IN_PROGRESS CodeBuilds jobs
    """
    cp_client = boto3.client('codepipeline')
    LOGGER.info(f"Looking for processes from CodePipeline: {pipeline_name}")
    try:
        _paginator = cp_client.get_paginator('list_pipeline_executions')
        _iterator = _paginator.paginate(pipelineName=pipeline_name)
        _running_executions = list(_iterator.search(
            "pipelineExecutionSummaries[?status == `InProgress`]"))
        LOGGER.info('Existing running executions lookup returned: %s', _running_executions)
        return _running_executions

    except Exception as err:
        LOGGER.error(err)
