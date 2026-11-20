# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import logging
import json

import boto3
from botocore.exceptions import ClientError

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)

SF_CLIENT = boto3.client("stepfunctions")


def lambda_handler(event, context):
    """
    Returns the status of a Step Function execution.

    Args:
        event (dict): The event passed by API Gateway
        context (object): Lambda Context runtime methods and attributes

    Returns:
        dict: API response with execution status
    """
    LOGGER.info("GetExecutionStatus invoked")

    try:
        query_params = event.get('queryStringParameters') or {}
        execution_arn = query_params.get('execution_arn')
        execution = query_params.get('execution')

        if not execution_arn and not execution:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": {
                        "code": "MISSING_PARAMETER",
                        "message": "Specify execution_arn or execution as query parameter"
                    }
                }),
                "isBase64Encoded": False,
                "headers": {"content-type": "application/json"}
            }

        # Build execution ARN if only name provided
        if not execution_arn:
            execution_arn = f"{os.environ['SF_EXECUTION_ARN_BASE']}:{execution}"

        LOGGER.info("Getting status for execution: %s", execution_arn)

        # Get StepFunction Execution Results
        sm_desc_response = SF_CLIENT.describe_execution(
            executionArn=execution_arn
        )
        response_body = {'Status': sm_desc_response.get('status')}

        if response_body['Status'] not in ['SUCCEEDED', 'FAILED']:
            sm_exec_hist_response = SF_CLIENT.get_execution_history(
                executionArn=execution_arn,
                reverseOrder=True,
                includeExecutionData=False
            )

            current_task = sm_exec_hist_response['events'][0].get(
                'stateEnteredEventDetails',
                {"name": "State machine is still starting, try again in a few seconds."}
            ).get('name')
            response_body['CurrentExecutionTask'] = current_task

        if response_body['Status'] == 'FAILED':
            response_body['Cause'] = sm_desc_response.get('cause', 'Unknown')

        return {
            "statusCode": 200,
            "body": json.dumps(response_body),
            "isBase64Encoded": False,
            "headers": {"content-type": "application/json"}
        }

    except SF_CLIENT.exceptions.ExecutionDoesNotExist:
        LOGGER.warning("Execution not found: %s", execution_arn if 'execution_arn' in dir() else execution)
        return {
            "statusCode": 404,
            "body": json.dumps({
                "error": {
                    "code": "NOT_FOUND",
                    "message": "Step Function execution not found"
                }
            }),
            "isBase64Encoded": False,
            "headers": {"content-type": "application/json"}
        }
    except ClientError as err:
        LOGGER.error("AWS API error in GetExecutionStatus: %s", err)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": {
                    "code": "AWS_ERROR",
                    "message": "Internal service error"
                }
            }),
            "isBase64Encoded": False,
            "headers": {"content-type": "application/json"}
        }
    except Exception as err:
        LOGGER.exception("Unexpected error in GetExecutionStatus")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Internal service error"
                }
            }),
            "isBase64Encoded": False,
            "headers": {"content-type": "application/json"}
        }
