# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import os
import tempfile
import zipfile
import boto3
from helper import (
    get_pipeline_s3_src_config,
    update_account_config_file,
    validate_ou_in_config,
    build_root_email_address,
    zip_directory,
    HelperCodePipeline
)

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)

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

    s3_client = boto3.client("s3")
    s3_resouce = boto3.resource("s3")
    cp_client = boto3.client("codepipeline")

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

            LOGGER.info("Account_info: %s", account_info)

            # Pull source file down from S3
            s3_bucket, s3_object_key = get_pipeline_s3_src_config(
                client=cp_client
            )
            s3_file = s3_object_key.split("/")[-1]

            with tempfile.TemporaryDirectory() as tmpdir:
                # Download file
                s3_resouce.Bucket(s3_bucket).download_file(s3_object_key, tmpdir+"/"+s3_file)
                LOGGER.info("Temporary S3 File location: %s", tmpdir+"/"+s3_file )

                # Unzip archive
                with zipfile.ZipFile(tmpdir+"/"+s3_file, 'r') as zip_ref:
                    zip_ref.extractall(tmpdir+"/unzipped")
                    print(tmpdir+"/unzipped")

                    validate_ou_in_config(
                        path_to_file=tmpdir+"/unzipped/organization-config.yaml",
                        target_ou_name=account_info["ManagedOrganizationalUnit"]
                    )

                    update_needed_bool = update_needed == 'true'
                    update_account_config_file(
                        path_to_file=tmpdir+"/unzipped/accounts-config.yaml",
                        account_info=account_info,
                        force_update=update_needed_bool
                    )

                    new_zip_file = zip_directory(
                        directory_path=tmpdir+"/unzipped/",
                        zip_file_name="aws-accelerator-config"
                    )

                    print(f"Uploading {new_zip_file} to {s3_bucket}/{s3_object_key}")
                    s3_client.upload_file(
                        Filename=new_zip_file,
                        Bucket=s3_bucket,
                        Key=s3_object_key
                    )

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

        LOGGER.info("Payload: %s", payload)
        return payload

    except Exception as e:
        LOGGER.exception(e)
        raise TypeError(str(e)) from e
