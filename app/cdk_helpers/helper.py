# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_cdk import SecretValue, aws_ssm as ssm


def get_secret_value(secrets_name: str) -> str:
    """Retrieves the value of a secret from AWS Secrets Manager.

    Args:
        secrets_name (str): The name of the secret. Can be the secret ID
            or a JSON field in the format "secret_id.json_field"

    Returns:
        str: The value of the secret.

    Raises:
        ValueError: If secrets_name is empty or None
    """
    if not secrets_name:
        raise ValueError("secrets_name cannot be empty or None")

    # Split the secrets_name once and store result
    parts = secrets_name.split(".", 1)  # maxsplit=1 since we only need at most 2 parts

    # Use dict for parameter construction
    params = {"secret_id": parts[0]}

    # Only add json_field if it exists
    if len(parts) > 1:
        params["json_field"] = parts[1]

    return SecretValue.secrets_manager(**params).to_string()


def get_ssm_value(scope, parameter_name: str):
    """Retrieves the value of a Systems Manager parameter.

    Args:
        scope (cdk.Construct): The construct scope.
        parameter_name (str): The name of the SSM parameter.

    Returns:
        str: The value of the SSM parameter.

    This function retrieves the value of an SSM parameter by name. It first uses
    the CDK's value_from_lookup method to get the parameter value. If the value
    contains the string 'dummy-value', it will return either a hardcoded ARN
    or the string 'dummy-value' itself. Otherwise it simply returns the
    original value retrieved from SSM.
    """
    _value = ssm.StringParameter.value_from_lookup(scope, parameter_name)
    if "dummy-value" in _value and "arn" in _value.lower():
        return "arn:aws:service:us-east-1:123456789012:entity/dummy-value"
    if "dummy-value" in _value:
        return "dummy-value"

    return _value


def replace_ssm_in_config(scope, temp_config: dict) -> dict:
    """Replaces SSM and secret values in a configuration dictionary.

    Args:
        scope (cdk.Construct): The construct scope.
        temp_config (dict): The configuration dictionary.

    Returns:
        dict: The updated configuration dictionary with SSM and secret values replaced.
    """
    def process_value(value, parent_dict, key=None, list_index=None):
        """Helper function to process individual values"""
        if isinstance(value, str):
            if "SSM:" in value:
                new_value = get_ssm_value(scope, parameter_name=value.replace("SSM:", ""))
                if list_index is not None:
                    parent_dict[key][list_index] = new_value
                else:
                    parent_dict[key] = new_value
            elif "SECRET:" in value:
                new_value = get_secret_value(secrets_name=value.replace("SECRET:", ""))
                if list_index is not None:
                    parent_dict[key][list_index] = new_value
                else:
                    parent_dict[key] = new_value
        return value

    def recursive_replace(config):
        """Recursively process all values in the configuration"""
        if isinstance(config, dict):
            for key, value in config.items():
                if isinstance(value, (dict, list)):
                    recursive_replace(value)
                else:
                    process_value(value, config, key)
        elif isinstance(config, list):
            for i, item in enumerate(config):
                if isinstance(item, dict):
                    recursive_replace(item)
                else:
                    process_value(item, config, list_index=i)

    recursive_replace(temp_config)
    return temp_config
