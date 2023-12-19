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
    return 60


def generate_sf_exec_name(account_name: str, client: boto3.client, dry_run=None) -> str:
    """ Generates a Step Function execution name, based on the number of previous execution

    Args:
        account_name (str): The name in which the requester would like the account
        client (boto3.client): boto3 client for Step Function
        dry_run (bool): Is this execution a dry run?

    Returns:
        str: Returns generated Step Function execution name
    """
    # Get number of executions with that account name in execution name
    count = 0

    paginator = client.get_paginator("list_executions")
    for page in paginator.paginate(stateMachineArn=statemachine_arn):
        for ex in page['executions']:
            if account_name in ex['name']:
                count = (count + 1)

    # If count is above 0 then append execution name with the next digit
    if count > 0:
        name = f"{account_name}-{str(count).zfill(2)}"
    else:
        name = account_name

    return name


class ParseTags(Action):
    """Class to parse string of KEY1=VALUE1 KEY2=VALUE2
    passed as an argument and turn it into a python list of
    dictionaries of format {"Key": <passed in key>, "Value": <passed in value>}
    to be able to be used as tags on the new account. Inherits argparse.Action
    parent class and overrides __call__ function of parent class.
    """

    def __call__(self, parser, namespace, values, option_string=None):
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
                            required=True, help='Control Tower - Account Name')
        parser.add_argument('-s', '--support-dl', dest='support_dl',
                            required=True, help='Account Support Distribution List')
        parser.add_argument('-m', '--managed-org-unit', dest='managed_org_unit',
                            required=True, help='Control Tower - Managed Organizational Unit')
        parser.add_argument('-p', '--purpose', dest='purpose',
                            required=True, help='The purpose of the account')

        # Active Directory Group(s)
        parser.add_argument('-ad', '--ad-integration', dest='ad_integration',
                            required=False, help='Azure Active Directory Group integration with Permission Set')
        
        # OPTIONAL
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
            {"Key": "support-dl", "Value": args.support_dl},
            {"Key": "purpose", "Value": args.purpose}
        ]

        if args.account_tags:
            account_tags.extend(args.account_tags) 

        # Setup Step Function input
        sf_input = {
            "AccountInfo": {
                "ForceUpdate": args.force_update,
                "AccountName": args.account_name,
                "Purpose": args.purpose,
                "SupportDL": args.support_dl,
                "ManagedOrganizationalUnit": args.managed_org_unit,
                "AccountTags": account_tags,
                "BypassCreation": args.bypass_creation
            }
        }
        
        if args.ad_integration:
            sf_input['AccountInfo']['ADIntegration'] = json.loads(args.ad_integration)

        # Get AWS Management Account if not specified in the argument and set arn variables
        current_account_id = STS_CLIENT.get_caller_identity()["Account"]

        statemachine_arn = f"arn:aws:states:{args.region}:{current_account_id}:stateMachine:CreateAccount"
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
                    input=json.dumps(sf_input),
                )
                break

            except (sf_client.exceptions.ExecutionAlreadyExistsx) as err:
                exec_count = (exec_count + 1)
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
