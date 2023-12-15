# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import json
import logging
import boto3
from account_creation_helper import (
    HelperCodePipeline,
    HelperCodeBuild
)

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)

SC_CLIENT = boto3.client('servicecatalog')


class CodePipelineException(Exception):
    """Custom Exception"""


class ServiceCatalogException(Exception):
    """Custom Exception"""


def search_provisioned_products(search_pp_name, client: boto3.client) -> dict:
    """Search for existing Service Catalog Provisioned Products. If it's not found
        then will search for any in-progress deployments since Control Tower has a
        serial method of deploying accounts.

    Args:
        search_pp_name (str): Service Catalog Provisioned Product Name to search for
        client (boto3.client): Boto3 Client for Service Catalog

    Returns:
        dict: Service Catalog Provisioned
    """
    LOGGER.info("Searching for %s", str(search_pp_name))
    response = client.search_provisioned_products(
        AccessLevelFilter={
            'Key': 'Account',
            'Value': 'self'
        },
        Filters={
            'SearchQuery': [f"name:{search_pp_name}"]
        }
    )
    if len(response['ProvisionedProducts']) > 0:
        provisioned_product = response['ProvisionedProducts'][0]
        LOGGER.info(f"Found {provisioned_product}")

        # Removing Create time since it doesn't serializable JSON well
        del provisioned_product['CreatedTime']
        return provisioned_product

    LOGGER.info(
        f"Did not find {search_pp_name}.")


def get_service_catalog_info(payload: dict) -> dict:
    outputs = {}

    # Look for account name in Service Catalog Provisioned Product list
    provisioned_product = search_provisioned_products(
        search_pp_name=payload['AccountInfo']['AccountName'],
        client=SC_CLIENT
    )
    LOGGER.debug(f"provisioned_product: {provisioned_product}")

    if provisioned_product:
        status = provisioned_product.get('Status')

        if status in ('TAINTED', 'ERROR'):
            raise ServiceCatalogException("There is a problem with the Service Catalog Product. ",
                                          provisioned_product)

        if status == 'AVAILABLE':
            outputs['AccountId'] = provisioned_product['PhysicalId']
            outputs['ProvisionedProductId'] = provisioned_product['Id']
            outputs['ProvisionedProductName'] = provisioned_product['Name']
            return outputs

    else:
        raise ServiceCatalogException(
            "Unable to find provisioned product in Service Catalog to get account information")


def lambda_handler(event, context):
    """This function will get the AWS Service Catalog / Control Tower Account Deployment status.

    Args:
        event (dict): Event information passed in by the AWS Step Functions
        context (object): Lambda Function context information

    Returns:
        dict: Payload with additional values for Account Status. This will be passed to the next step in the
        Step Function.
    """
    print(json.dumps(event))
    payload = event['Payload']

    try:

        if payload['AccountInfo'].get('BypassCreation') == 'false':
            pipeline = HelperCodePipeline(
                os.getenv('LZA_CODEPIPELINE_NAME', 'AWSAccelerator-Pipeline'))

            pipeline_execution_id = payload['CodePipeline']['CodePipelineExecutionId']
            pipeline_status = pipeline.status(pipeline_execution_id)

            if pipeline_status == 'Succeeded':
                payload['Account'] = {"Status": "SUCCESS",
                                    "Outputs": get_service_catalog_info(payload=payload)}

            elif pipeline_status == "InProgress":
                payload['Account'] = {"Status": "UNDER_CHANGE"}

            elif pipeline_status == "Failed":
                LOGGER.debug(
                    'CodePipeline is in a Failed status, gathering further information')
                failed_action = pipeline.get_failed_action(pipeline_execution_id)
                LOGGER.debug('Retrieved failed Pipeline action: %s', failed_action)
                error_output = {
                    'FailedActionName': failed_action['actionName'],
                    'FailedActionStage': failed_action['stageName'],
                    'FailedActionOutput': failed_action['output']
                }
                LOGGER.debug('Checking if the failed action is a CodeBuild job')
                if failed_action.get('input', {}).get('actionTypeId', {}).get('provider') == "CodeBuild":
                    LOGGER.debug(
                        'Failed action is a CodeBuild job, retrieving details')
                    codebuild_info = HelperCodeBuild(
                        failed_action['output']['executionResult']['externalExecutionId'])
                    error_output['FailedCodeBuildInfo'] = codebuild_info.get_failed_phase_info(
                    )
                raise CodePipelineException(error_output)

            else:
                raise CodePipelineException(
                    f"The CodePipeline Execution ID {pipeline_execution_id} is stopped with status {pipeline_status}")

            payload['CodePipeline']['CodePipelineRunStatus'] = pipeline_status

        elif payload['AccountInfo'].get('BypassCreation') == 'true': 
            LOGGER.info("Bypassing Account Status Check...")
            payload['Account'] = {
                "Status": "BYPASSED",
                "Outputs": get_service_catalog_info(payload=payload)
            }

        return payload

    except Exception as e:
        LOGGER.error(e)
        raise TypeError(str(e)) from e
