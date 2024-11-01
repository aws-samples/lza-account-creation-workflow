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

STS_CLIENT = boto3.client("sts")


def generate_sf_exec_name(account_name: str, statemachine_arn: str, client: boto3.client) -> str:
    """
    Generates a unique Step Function execution name based on the account name and previous executions.

    This function creates a unique name for a Step Function execution by appending a number to the
    account name if there have been previous executions with the same account name. It queries the
    Step Function's execution history to determine the appropriate suffix.

    Args:
        account_name (str): The desired name for the AWS account. This will be used as the base for
                            the execution name.
        statemachine_arn (str): The Amazon Resource Name (ARN) of the Step Function state machine.
        client (boto3.client): A boto3 client for AWS Step Functions.

    Returns:
        str: A unique execution name for the Step Function. If this is the first execution for the
             given account name, it will be the account name itself. Otherwise, it will be in the
             format "{account_name}-{nn}", where nn is a zero-padded two-digit number representing
             the execution count.
    """
    # Get number of executions with that account name in execution name
    count = 0

    paginator = client.get_paginator("list_executions")
    for page in paginator.paginate(stateMachineArn=statemachine_arn):
        for ex in page['executions']:
            if account_name in ex['name']:
                count = count + 1

    # If count is above 0 then append execution name with the next digit
    if count > 0:
        name = f"{account_name}-{str(count).zfill(2)}"
    else:
        name = account_name

    return name


def lambda_handler(event, context):
    """
    Handles Lambda function requests to initiate a Step Function execution for account creation.

    This function processes incoming requests, either from API Gateway or directly (e.g., from Terraform),
    extracts necessary parameters, and starts a Step Function execution for creating an AWS account.
    It handles required parameters such as account name, support distribution list, and managed 
    organizational unit, as well as optional parameters like Active Directory integration.

    Args:
        event (dict): The event passed by Lambda. It can be in two formats:
            - API Gateway format: Contains a 'body' key with a JSON string of parameters.
            - Direct invocation format: The event itself is a dictionary of parameters.
        context (object): Lambda Context runtime methods and attributes. This object provides
            information about the current execution environment.

    Returns:
        dict: The API response including:
            - statusCode (int): HTTP status code (200 for success, 400 for bad request, 500 for server error)
            - body (str): A JSON string containing:
                - message (str): A description of the result
                - data (dict): Additional data about the Step Function execution, including:
                    - executionArn (str): The ARN of the started Step Function execution
                    - startDate (str): The start date and time of the execution

    Raises:
        Exception: If there's an error during execution, it's caught and returned as a 500 response.
    """
    LOGGER.info(json.dumps(event))
    response = 404

    # Used by API Gateway
    if event.get('body'):
        params = json.loads(event['body'])

    # Used by Terraform
    elif isinstance(event, dict):
        params = event

    try:
        # REQUIRED
        account_name = params['account_name']
        support_dl = params['support_dl']
        managed_org_unit = params['managed_org_unit']

        # Active Directory Group(s)
        ad_integration = params.get('ad_integration')

        # OPTIONAL
        account_email = params.get('account_email')
        region = params.get('region', os.environ['AWS_REGION'])
        force_update = params.get('force_update', "false")
        bypass_creation = params.get('bypass_creation', "false")
        additional_tags = params.get('account_tags')

        # Setup required tags
        account_tags = [
            {"Key": "account-name", "Value": account_name},
            {"Key": "vendor", "Value": "aws"},
            {"Key": "product-version", "Value": "1.0.0"},
            {"Key": "support-dl", "Value": support_dl}
        ]

        # Add the additonal tags to the required account tags
        if additional_tags:
            account_tags.extend(additional_tags) 

        # Setup Step Function input
        sf_input = {
            "AccountInfo": {
                "ForceUpdate": force_update,
                "AccountName": account_name,
                "AccountEmail": account_email,
                "SupportDL": support_dl,
                "ManagedOrganizationalUnit": managed_org_unit,
                "AccountTags": account_tags,
                "BypassCreation": bypass_creation   
            }
        }

        if ad_integration:
            sf_input['AccountInfo']['ADIntegration'] = ad_integration

        # Get AWS Management Account if not specified in the argument and set arn variables
        current_account_id = STS_CLIENT.get_caller_identity()["Account"]
        statemachine_arn = f"arn:aws:states:{region}:{current_account_id}:stateMachine:{os.environ['STEPFUNCTION_NAME']}"
        sf_client = boto3.client(service_name='stepfunctions')

        sf_exec_name = generate_sf_exec_name(
            account_name=account_name, 
            statemachine_arn=statemachine_arn,
            client=sf_client
        )

        exec_count = 0
        while True:
            try:
                # Start step function
                start_exec_response = sf_client.start_execution(
                    stateMachineArn=statemachine_arn,
                    name=sf_exec_name,
                    input=json.dumps(sf_input),
                )
                break

            except (sf_client.exceptions.ExecutionAlreadyExists) as err:
                exec_count = exec_count + 1
                sf_exec_name = f"{account_name}-{str(exec_count).zfill(2)}"
                LOGGER.debug(err)
                LOGGER.debug(f'Incrementing count and trying with execution name:{sf_exec_name}')

        # Get execution arn
        sm_exec_arn = start_exec_response['executionArn']
        response_body = {"StepFunctionExecutionArn": sm_exec_arn}

        # Building response for Api Call
        response = {
            "statusCode": 200,
            "body": json.dumps(response_body),
            "isBase64Encoded": False,
            "headers": {
                "content-type": "application/json"
            }
        }

    except Exception as err:
        LOGGER.exception(err)

        # Building response for Api Call
        response = {
            "statusCode": 404,
            "body": f'{"Failure": {err}}',
            "isBase64Encoded": False,
            "headers": {
                "content-type": "application/json"
            }
        }

    finally:
        LOGGER.info(response)
        return response
