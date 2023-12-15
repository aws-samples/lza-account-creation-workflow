# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_cdk import aws_ssm as ssm


def create_ssm_parameter(scope, parameter_key: str, parameter_value: str, 
                         parameter_type: str = "string", parameter_description: str = '') -> None:
    if parameter_type == 'string':
        ssm.StringParameter(scope, f"rSsm{parameter_key.title().replace('/','')}",
            parameter_name=parameter_key,
            string_value=parameter_value,
            description=parameter_description
        )
