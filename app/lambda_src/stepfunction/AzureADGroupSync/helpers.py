# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import boto3


def get_secret_value(secret_name: str) -> dict:
    """Get value of secret from Secrets Manager

    Args:
        secret_name (str): The name (aka ID) of the secret to lookup

    Returns:
        dict: boto3 response dictionary
    """
    sm_client = boto3.client('secretsmanager')
    response = sm_client.get_secret_value(
        SecretId=secret_name
    )
    return response['SecretString']
