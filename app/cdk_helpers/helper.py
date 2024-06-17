# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_cdk import (
    aws_ssm as ssm
)

def replace_ssm_in_config(scope, temp_config: dict) -> dict:
    """
    Replace SSM parameter values in a configuration dictionary.

    Args:
        scope (Construct): The scope in which to define this construct's resources.
        temp_config (dict): The configuration dictionary to replace SSM parameter values in.

    Returns:
        dict: The configuration dictionary with SSM parameter values replaced.
    """
    for key1, val1 in temp_config.items():
        if 'SSM:' in val1:
            temp_config[key1] = ssm.StringParameter.value_from_lookup(scope, val1.replace('SSM:', ''))

        if isinstance(val1, dict):
            for key2, val2 in val1.items():
                if isinstance(val2, str) and 'SSM:' in val2:
                    temp_config[key1][key2] = ssm.StringParameter.value_from_lookup(scope, val2.replace('SSM:', ''))

                if isinstance(val2, dict):
                    for key3, val3 in val2.items():
                        if isinstance(val3, str) and 'SSM:' in val3:
                            temp_config[key1][key2][key3] = ssm.StringParameter.value_from_lookup(scope, val3.replace('SSM:', ''))
    return temp_config
