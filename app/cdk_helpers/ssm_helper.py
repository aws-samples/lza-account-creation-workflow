# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_cdk import aws_ssm as ssm


def create_ssm_parameter(scope, parameter_key: str, parameter_value: str, 
                         parameter_type: str = "string", parameter_description: str = '') -> None:
    """
    Creates an AWS Systems Manager (SSM) parameter.

    Args:
        scope (Construct): The CDK construct scope in which to define this parameter.
        parameter_key (str): The name of the parameter.
        parameter_value (str): The value of the parameter.
        parameter_type (str, optional): The type of the parameter. Defaults to "string".
        parameter_description (str, optional): Description for the parameter. Defaults to ''.

    Returns:
        None
    """
    if parameter_type == 'string':
        ssm.StringParameter(scope, f"rSsm{parameter_key.title().replace('/','')}",
            parameter_name=parameter_key,
            string_value=parameter_value,
            description=parameter_description
        )
