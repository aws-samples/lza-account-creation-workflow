# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import time
import os
import tempfile
import zipfile

import boto3
from botocore.exceptions import ClientError

from helper import (
    get_pipeline_s3_src_config,
    update_account_config_file,
    validate_ou_in_config,
    build_root_email_address,
    zip_directory
)
from account_creation_helper import HelperCodePipeline

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)

S3_CLIENT = boto3.client("s3")
S3_RESOURCE = boto3.resource("s3")
CP_CLIENT = boto3.client("codepipeline")


class OuNotFoundException(Exception):
    """Custom exception"""


def lambda_handler(event, context):
    """Create/setup account(s) within a Control Tower ecosystem.

    Args:
        event (dict): Event information passed in by the AWS Step Functions
        context (object): Lambda Function context information

    Returns:
        dict: Payload values that will be passed to the next step in the Step Function
    """
    LOGGER.debug('Event: %s', json.dumps(event))
    payload = {}

    try:
        # If the Payload key is found this indicates that this isn't the first attempt
        #  and there may be a concurrent Account Factory job running
        if event.get('Payload'):
            account_info = event['Payload']['AccountInfo']
        else:
            account_info = event['AccountInfo']

        update_needed = account_info.get('ForceUpdate', 'false')

        # If no AccountEmail is provided generate one based on account name
        if not account_info.get('AccountEmail'):
            account_info['AccountEmail'] = build_root_email_address(
                account_name=account_info['AccountName']
            )

        if account_info.get('BypassCreation') == 'false':
            # Setup CodePipeline Class
            code_pipeline = HelperCodePipeline(
                os.getenv('LZA_CODEPIPELINE_NAME', 'AWSAccelerator-Pipeline')
            )

            LOGGER.info("Account_info: %s", account_info)

            # Pull source file down from S3
            s3_bucket, s3_object_key = get_pipeline_s3_src_config(
                client=CP_CLIENT
            )
            s3_file = s3_object_key.split("/")[-1]

            with tempfile.TemporaryDirectory() as tmpdir:
                # Download file
                S3_RESOURCE.Bucket(s3_bucket).download_file(
                    s3_object_key, tmpdir + "/" + s3_file
                )
                LOGGER.info("Temporary S3 File location: %s", tmpdir + "/" + s3_file)

                # Unzip archive
                with zipfile.ZipFile(tmpdir + "/" + s3_file, 'r') as zip_ref:
                    zip_ref.extractall(tmpdir + "/unzipped")
                    LOGGER.info("Extracted to: %s", tmpdir + "/unzipped")

                    validate_ou_in_config(
                        path_to_file=tmpdir + "/unzipped/organization-config.yaml",
                        target_ou_name=account_info["ManagedOrganizationalUnit"]
                    )

                    update_needed_bool = update_needed == 'true'
                    update_account_config_file(
                        path_to_file=tmpdir + "/unzipped/accounts-config.yaml",
                        account_info=account_info,
                        force_update=update_needed_bool
                    )

                    new_zip_file = zip_directory(
                        directory_path=tmpdir + "/unzipped/",
                        zip_file_name="aws-accelerator-config"
                    )

                    LOGGER.info(
                        "Uploading %s to %s/%s", new_zip_file, s3_bucket, s3_object_key
                    )
                    with open(new_zip_file, 'rb') as file:
                        upload_version = S3_CLIENT.put_object(
                            Bucket=s3_bucket,
                            Key=s3_object_key,
                            Body=file
                        )['VersionId']

            # Check if push to S3 triggered the pipeline
            LOGGER.info("Checking if upload triggered the Pipeline")
            pipeline_execution_id = None
            sleep_duration = 3

            LOGGER.info("Looking for S3 Object Version: %s", upload_version)
            # Wait a total of 21 seconds to see if CodePipeline is triggered automatically
            for count in range(7):
                LOGGER.info(
                    "Sleeping 3 seconds to see if upload triggers pipeline (count:%s)", count
                )
                time.sleep(sleep_duration)

                pipeline_executions = code_pipeline.other_running_executions()
                for execution in pipeline_executions:
                    for source_revision in execution['sourceRevisions']:
                        if (source_revision['actionName'] == 'Configuration' and
                                source_revision['revisionId'] == upload_version):
                            pipeline_execution_id = execution['pipelineExecutionId']
                            LOGGER.info(
                                "Upload triggered Pipeline Execution: %s",
                                pipeline_execution_id
                            )

                if pipeline_execution_id:
                    break

            if not pipeline_execution_id:
                LOGGER.info("Upload did NOT trigger pipeline. Starting Pipeline Execution")
                pipeline_execution_id = code_pipeline.start_execution()

            pipeline_execution_status = code_pipeline.status(pipeline_execution_id)

            payload['CodePipeline'] = {
                'CodePipelineRunStatus': pipeline_execution_status,
                'CodePipelineExecutionId': pipeline_execution_id
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

        LOGGER.info("Payload: %s", payload)
        return payload

    except ClientError as client_err:
        LOGGER.error(
            "AWS API error during account creation: %s", client_err.response['Error']['Message']
        )
        raise RuntimeError(str(client_err)) from client_err
    except KeyError as key_err:
        LOGGER.error("Missing required key in event payload: %s", key_err)
        raise RuntimeError(str(key_err)) from key_err
    except (OSError, zipfile.BadZipFile) as file_err:
        LOGGER.error("File operation error: %s", file_err)
        raise RuntimeError(str(file_err)) from file_err
    except Exception as e:
        LOGGER.exception("Unexpected error during account creation")
        raise RuntimeError(str(e)) from e
