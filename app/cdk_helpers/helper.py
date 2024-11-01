# (c) 2024 Amazon Web Services, Inc. or its affiliates. All Rights Reserved.
# This AWS Content is provided subject to the terms of the AWS Customer Agreement
# available at http://aws.amazon.com/agreement or other written agreement between
# Customer and Amazon Web Services, Inc.

from aws_cdk import SecretValue, aws_ssm as ssm


def get_secret_value(secrets_name: str):
    """Retrieves the value of a secret from AWS Secrets Manager.

    Args:
        secrets_name (str): The name of the secret. Can be the secret ID
            or a JSON field in the format "secret_id.json_field".

    Returns:
        str: The value of the secret.

    This function retrieves secrets stored in AWS Secrets Manager. It handles
    both cases where secrets_name is just the secret ID, and where it contains
    the secret ID and JSON field separated by a period. The secret value is
    returned after retrieving it from Secrets Manager. If the secrets_name
    contains a period, it is split into secret ID and JSON field before retrieval.
    """
    if len(secrets_name.split(".")) == 1:
        _value = SecretValue.secrets_manager(secret_id=secrets_name).to_string()

    if len(secrets_name.split(".")) > 1:
        _secrets_id = secrets_name.split(".")[0]
        _secret_json = secrets_name.split(".")[1]
        _value = SecretValue.secrets_manager(
            secret_id=_secrets_id, json_field=_secret_json
        ).to_string()

    return _value


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


def replace_ssm_in_config(scope, input_config):
    """Replaces SSM and secret values in a configuration dictionary.

    Args:
        scope (cdk.Construct): The construct scope.
        input_config: The configuration dictionary, list, or value.

    Returns:
        The updated configuration with SSM and secret values replaced.

    This function recursively searches the configuration for strings
    containing "SSM:" or "SECRET:". These values are replaced by calling
    get_ssm_value() or get_secret_value() respectively. The configuration is
    searched at all levels to support nested structures. It handles different
    data types including dictionaries, lists, and strings, ensuring a thorough
    replacement process throughout the entire configuration structure.
    """
    if isinstance(input_config, dict):
        return {key: replace_ssm_in_config(scope, value) for key, value in input_config.items()}
    elif isinstance(input_config, list):
        return [replace_ssm_in_config(scope, item) for item in input_config]
    elif isinstance(input_config, str):
        if input_config.startswith("SSM:"):
            return get_ssm_value(scope, parameter_name=input_config[4:])
        elif input_config.startswith("SECRET:"):
            return get_secret_value(secrets_name=input_config[7:])
    return input_config
