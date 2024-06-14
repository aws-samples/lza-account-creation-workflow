# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import logging
import json
import boto3

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


def lambda_handler(event, context):
    """
    Handles Lambda function requests and returns responses.

    Args:
        event (dict): The event passed by Lambda 
        context (object): Lambda Context runtime methods and attributes

    Returns: 
        dict: The API response including statusCode and body
    """
    LOGGER.info(json.dumps(event))
    status_code = 404

    response_body = {}
    body = '{"message": "lambda did not complete"}'
    sf_client = boto3.client(service_name='stepfunctions')

    try:
        # Get StepFunction Execution or ExecutionArn from API Parameter 
        execution_arn = event['queryStringParameters'].get('execution_arn')
        execution = event['queryStringParameters'].get('execution')

        if not execution_arn and not execution:
            raise Exception("Please specify \"execution_arn\" or \"execution\" as API Parameter.")

        # Setup StepFunction Execution Arn if one is not setup
        if not execution_arn: 
            execution = event['queryStringParameters'].get('execution')
            execution_arn = f"{os.environ['SF_EXECUTION_ARN_BASE']}:{execution}"

        LOGGER.info(f"Getting Status for StepFunction Execution Arn: {execution_arn} ")

        # Get StepFunction Execution Results
        sm_desc_response = sf_client.describe_execution(
            executionArn=execution_arn
        )
        response_body['Status'] = sm_desc_response.get('status')

        if response_body['Status'] not in ['SUCCEEDED', 'FAILED']:
            sm_exec_hist_response = sf_client.get_execution_history(
                executionArn=execution_arn,
                reverseOrder=True,
                includeExecutionData=False
            )

            current_task = sm_exec_hist_response['events'][0].get('stateEnteredEventDetails', \
                {"name": "State machines is still starting, try again in a few seconds."}).get('name')
            response_body['CurrentExecutionTask'] = current_task 

        if response_body['Status'] == 'FAILED':
            response_body['Cause'] = sm_desc_response['cause']

        # Building response for Api Call
        status_code = 200
        body = json.dumps(response_body)

    except Exception as err:
        LOGGER.error(err)
        status_code = 404
        body = '{"Failure": "%s"}' % str(err)

    finally:
        response = {
            "statusCode": status_code,
            "body": body,
            "isBase64Encoded": False,
            "headers": {
                "content-type": "application/json"
            }
        }
        LOGGER.info(response)
        return response
