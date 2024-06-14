# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import re
import logging
import boto3

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


class ValidateSsm:
    """
    Validates SSM Parameters in AWS accounts.

    The class assumes an IAM role to make API calls. It contains
    a method to check if a given SSM parameter exists, returning the
    validation result.
    """
    creds = {}

    def __init__(self, assumed_creds: dict):
        # initialization logic
        self.creds = assumed_creds
        ssm_args = {"service_name": "ssm"}
        ssm_args.update(self.creds)
        self.ssm_client = boto3.client(**ssm_args)

    def ssm_parameter_exist(self, parameter_name: str):
        """
        Checks if an SSM parameter exists.

        Args: 
            parameter_name (str): Name of the parameter

        Returns:
            dict: Validation result
        """
        LOGGER.info(f"Checking if SSM Parameter ({parameter_name}) exists.")
        try:
            _parameter = self.ssm_client.get_parameter(Name=parameter_name)

        except Exception as err:
            if re.search(r'((ParameterNotFound))', str(err)):
                LOGGER.warning(str(err))
                _parameter = None

        if not _parameter:
            status = "Failed"
            validation_msg = f"SSM Parameter {parameter_name} does NOT exist in the newly created Account"
        else:
            status = "Passed"
            validation_msg = f"SSM Parameter {parameter_name} exists"

        return {
            "Service": f"SsmParameterValidation_{parameter_name}",
            "Status": status,
            "Message": validation_msg
        }
