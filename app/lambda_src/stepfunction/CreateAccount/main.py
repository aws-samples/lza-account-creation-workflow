# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import os
import tempfile
import boto3
from helper import (
    update_account_config_file,
    validate_ou_in_config,
    build_root_email_address,
    HelperCodePipeline
)
from git_helper import GHCodeCommit, GHGit

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)

SC_CLIENT = boto3.client('servicecatalog')


class OuNotFoundException(Exception):
    """Custom exception"""


def lambda_handler(event, context):
    """This function will create/setup account(s) that will live within a Control Tower ecosystem.

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

        update_needed = account_info.get('ForceUpdate', 'false')

        # If not AccountEmail is provided generate one based on account name
        if not account_info.get('AccountEmail'):
            account_info['AccountEmail'] = build_root_email_address(account_name=account_info['AccountName'])

        if account_info.get('BypassCreation') == 'false':
            # Setup CodePipeline Class
            code_pipeline = HelperCodePipeline(
                os.getenv('LZA_CODEPIPELINE_NAME', 'AWSAccelerator-Pipeline'))

            code_commit_repo_name = os.getenv(
                'LZA_CONFIG_REPO_NAME', "aws-accelerator-config")

            LOGGER.info(f"Account_info:{account_info}")

            code_commit_repo = GHCodeCommit(
                code_commit_repo_name, boto3.session.Session())

            with tempfile.TemporaryDirectory() as tmpdir:
                lambda_git = GHGit(tmpdir)
                lambda_git.clone(code_commit_repo)

                validate_ou_in_config(
                    path_to_file=f'{tmpdir}/organization-config.yaml', 
                    target_ou_name=account_info["ManagedOrganizationalUnit"]
                )

                update_needed_bool = update_needed == 'true'
                update_account_config_file(
                    path_to_file=f'{tmpdir}/accounts-config.yaml',
                    account_info=account_info,
                    force_update=update_needed_bool
                )

                lambda_git.create_commit(
                    [f'{tmpdir}/accounts-config.yaml'], 
                    f"Adding new account: {account_info['AccountName']}"
                )
                lambda_git.push()

            pipeline_execution_id = code_pipeline.start_execution()
            pipeline_execution_status = code_pipeline.status(pipeline_execution_id)

            payload['CodePipeline'] = {
                'CodePipelineRunStatus': pipeline_execution_status,
                'CodePipelineExecutionId':pipeline_execution_id
            }

            # Set Run Status to see if SC is updating or creating
            payload['ServiceCatalogEvent'] = {}
            if update_needed:
                payload['ServiceCatalogEvent']['ServiceCatalogRunStatus'] = "Update"
            else:
                payload['ServiceCatalogEvent']['ServiceCatalogRunStatus'] = "Create"

        elif account_info.get('BypassCreation') == 'true':
            LOGGER.info("Bypassing Account Creation...")

        # Add AccountInfo to payload
        payload['AccountInfo'] = account_info

        LOGGER.info(f"Payload: {payload}")
        return payload

    except Exception as e:
        LOGGER.exception(e)
        raise TypeError(str(e)) from e
