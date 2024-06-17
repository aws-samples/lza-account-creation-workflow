# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import logging
import json
import time
from argparse import ArgumentParser, Action
import boto3

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)

STS_CLIENT = boto3.client("sts")


def check_delay() -> int:
    """
    Returns a fixed delay value of 60 seconds.

    Returns:
        int: The delay value of 60 seconds.

    This function is a simple utility that returns a constant value of 60,
    representing a delay in seconds. It does not take any arguments and
    always returns the same value.
    """
    return 60


def generate_sf_exec_name(account_name: str, client: boto3.client) -> str:
    """
    Generate a unique execution name for a Step Function based on the provided account name.

    Args:
        account_name (str): The name of the account for which the execution name is being generated.
        client (boto3.client): A Boto3 client for AWS Step Functions.

    Returns:
        str: A unique execution name for the Step Function.

    The function generates a unique execution name by appending a two-digit number to the account name
    if there are existing executions with the same account name. The number is incremented based on the
    count of existing executions with the same account name.

    If there are no existing executions with the provided account name, the function returns the account
    name as the execution name.
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


class ParseTags(Action):
    """
    A custom Action class for parsing command-line arguments into a list of key-value tag pairs.

    This class inherits from the `Action` class provided by the `argparse` module and overrides
    the `__call__` method to handle the parsing of tag arguments.

    When this action is encountered during argument parsing, it creates an empty list in the
    namespace object specified by `self.dest`. Then, for each value provided, it splits the
    value on the '=' character to obtain the key and value components. It appends a dictionary
    with the 'Key' and 'Value' keys to the list in the namespace object.
    """

    def __call__(self, parser, namespace, values, option_string=None):
        """
        Parse the provided tag values and store them as a list of dictionaries in the namespace object.

        Args:
            parser (ArgumentParser): The argument parser object.
            namespace (Namespace): The namespace object to store the parsed tags.
            values (list): The list of tag values to be parsed.
            option_string (str, optional): The option string that triggered this action.

        This method creates an empty list in the namespace object specified by `self.dest`.
        For each value in the `values` list, it splits the value on the '=' character to obtain
        the key and value components. It then appends a dictionary with the 'Key' and 'Value'
        keys to the list in the namespace object.
        """
        setattr(namespace, self.dest, list())
        for value in values:
            key, value = value.split('=')
            getattr(namespace, self.dest).append(
                {"Key": key, "Value": value})


if __name__ == "__main__":
    LOGGER.debug("Starting script...")

    try:
        parser = ArgumentParser()
        # REQUIRED
        parser.add_argument('-a', '--account-name', dest='account_name',
                            required=True, help='Landing Zone Accelerator - AWS Account Name')
        parser.add_argument('-s', '--support-dl', dest='support_dl',
                            required=True, help='Account Support Distribution List')
        parser.add_argument('-m', '--managed-org-unit', dest='managed_org_unit',
                            required=True, help='Landing Zone Accelerator - Managed Organizational Unit')

        # Active Directory Group(s)
        parser.add_argument('-ad', '--ad-integration', dest='ad_integration', type=json.loads,
                            required=False, help='Azure Active Directory Group integration with Permission Set')

        # OPTIONAL
        parser.add_argument('-e', '--account-email', dest='account_email', default='',
                            required=False, help='Landing Zone Accelerator - AWS Account Email')
        parser.add_argument('-r', '--region', dest='region', default='us-east-1',
                            required=False, help='AWS Region the Create Account Step Function resides')
        parser.add_argument('-f', '--force-update', dest='force_update', choices=['true', 'false'],
                            default='false', help='Force a Landing Zone Accelerator Update [ true | false ]', type=str.lower)
        parser.add_argument('-b', '--bypass-creation', dest='bypass_creation', choices=['true', 'false'],
                            default='false', help='Bypass adding account to accounts-config.yaml and LZA CodePipeline Run [ true | false ]',
                            type=str.lower)
        parser.add_argument('-t', '--tags', dest='account_tags', required=False, metavar='KEY=VALUE', nargs='+', action=ParseTags,
                            help="Enter tags as key value pairs of KEY=VALUE with no spaces between the = sign. Add a space \
                                between multiple key value pairs. If the VALUE has spaces in it wrap the value in double quotes.")

        args, _ = parser.parse_known_args()

        account_tags = [
            {"Key": "account-name", "Value": args.account_name},
            {"Key": "vendor", "Value": "aws"},
            {"Key": "product-version", "Value": "1.0.0"},
            {"Key": "support-dl", "Value": args.support_dl}
        ]

        if args.account_tags:
            account_tags.extend(args.account_tags)

        # Setup Step Function input
        sf_input = {
            "AccountInfo": {
                "ForceUpdate": args.force_update,
                "AccountName": args.account_name,
                "AccountEmail": args.account_email,
                "SupportDL": args.support_dl,
                "ManagedOrganizationalUnit": args.managed_org_unit,
                "AccountTags": account_tags,
                "BypassCreation": args.bypass_creation   
            }
        }

        if args.ad_integration:
            sf_input['AccountInfo']['ADIntegration'] = args.ad_integration

        # Get AWS Management Account if not specified in the argument and set arn variables
        current_account_id = STS_CLIENT.get_caller_identity()["Account"]

        statemachine_arn = f"arn:aws:states:{args.region}:{current_account_id}:stateMachine:LZA-CreateAccount"
        sf_client = boto3.client(service_name='stepfunctions')

        sf_exec_name = generate_sf_exec_name(
            account_name=args.account_name, client=sf_client
        )

        exec_count = 0
        while True:
            try:
                # Start step function
                start_exec_response = sf_client.start_execution(
                    stateMachineArn=statemachine_arn,
                    name=sf_exec_name,
                    input=json.dumps(sf_input)
                )
                break

            except (sf_client.exceptions.ExecutionAlreadyExistsx) as err:
                exec_count = exec_count + 1
                sf_exec_name = f"{args.account_name}-{str(exec_count).zfill(2)}"
                LOGGER.debug(
                    f'Incrementing count and trying with execution name:{sf_exec_name}')

        # Get execution arn
        sm_exec_arn = start_exec_response['executionArn']
        LOGGER.debug(start_exec_response)
        time.sleep(check_delay())

        sm_desc_response = sf_client.describe_execution(
            executionArn=sm_exec_arn
        )

        LOGGER.debug(sm_desc_response)

        # Keep checking step function execution to ensure it finished
        while sm_desc_response['status'] == 'RUNNING':
            sm_desc_response = sf_client.describe_execution(
                executionArn=sm_exec_arn
            )
            time.sleep(check_delay())
            LOGGER.debug(sm_desc_response)

        if sm_desc_response.get('status') == 'FAILED':
            print(json.loads(sm_desc_response['cause']))
        elif sm_desc_response.get('status') == 'ABORTED':
            print("StepFunction has been ABORTED.")
        elif sm_desc_response.get('status') == 'TIMED_OUT':
            print("StepFunction has TIMED_OUT.")    
        else:
            print(json.loads(sm_desc_response['output'])['Payload'])

    except Exception as e:
        LOGGER.exception(e)
