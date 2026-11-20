# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import re
from aws_cdk import Annotations, SecretValue, aws_ssm as ssm

# Values returned while CDK has not resolved the SSM context lookup yet
# (first synthesis pass). They keep IAM resource ARNs well formed.
PLACEHOLDER_ARN = "arn:aws:service:us-east-1:123456789012:entity/dummy-value"
PLACEHOLDER_VALUE = "dummy-value"

# Config keys under appInfrastructure that are read from SSM when the LZA
# pipeline source is S3, with the format their resolved value must have.
LZA_SSM_VALUE_PATTERNS = {
    'lzaPipelineKmsKeyArn': (
        r"arn:aws[a-z-]*:kms:[a-z0-9-]+:\d{12}:key/[0-9a-zA-Z-]+",
        "a KMS key ARN"
    ),
    'lzaConfigBucketName': (
        r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]",
        "an S3 bucket name"
    )
}


def get_ssm_parameter_names(app_config: dict, keys) -> list:
    """Lists the SSM parameter names that the given config keys reference.

    Only values written as "SSM:<parameter name>" are returned. Nothing is
    returned when the LZA pipeline source is not S3, because these values are
    only used for the S3 source. Call this before replace_ssm_in_config, which
    replaces the "SSM:" values in place.

    Args:
        app_config (dict): The appInfrastructure section of the config.
        keys: The config keys to look at.

    Returns:
        list: The SSM parameter names, in the order of the keys.
    """
    if app_config.get('lzaPipelineSource', 'S3') != 'S3':
        return []
    names = []
    for key in keys:
        value = app_config.get(key)
        if isinstance(value, str) and value.startswith("SSM:"):
            names.append(value[len("SSM:"):])
    return names


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
    the CDK's value_from_lookup method to get the parameter value. While CDK has
    not resolved the lookup (first synthesis pass), the lookup returns a dummy
    value and a well-formed placeholder is returned instead. After the lookup is
    resolved, an empty value adds a CDK error annotation that names the parameter,
    so that synth exits non-zero. No exception is raised.
    """
    _value = ssm.StringParameter.value_from_lookup(scope, parameter_name)
    if "dummy-value" in _value and "arn" in _value.lower():
        return PLACEHOLDER_ARN
    if "dummy-value" in _value:
        return PLACEHOLDER_VALUE
    if not _value or not _value.strip():
        Annotations.of(scope).add_error(
            f"SSM parameter '{parameter_name}' is empty. Set it to the value "
            "that deploy-config.yaml expects."
        )

    return _value


def validate_ssm_config_value(scope, parameter_name: str, value: str, pattern: str, description: str) -> None:
    """Adds a CDK error annotation when a resolved SSM value has an invalid format.

    Placeholder values are skipped because they only appear while CDK has not
    resolved the lookup yet.

    Args:
        scope (cdk.Construct): The construct scope the annotation is added to.
        parameter_name (str): The name of the SSM parameter the value came from.
        value (str): The resolved value.
        pattern (str): Regular expression the value must fully match.
        description (str): Human-readable description of the expected value.
    """
    if value in (PLACEHOLDER_ARN, PLACEHOLDER_VALUE) or not value:
        # Empty values already carry an annotation from get_ssm_value
        return
    if not re.fullmatch(pattern, value):
        Annotations.of(scope).add_error(
            f"SSM parameter '{parameter_name}' does not hold {description}."
        )


def replace_ssm_in_config(scope, input_config: dict) -> dict:
    """Replaces SSM and secret values in a configuration dictionary.

    Args:
        scope (cdk.Construct): The construct scope.
        input_config (dict): The configuration dictionary.

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

    recursive_replace(input_config)
    return input_config
