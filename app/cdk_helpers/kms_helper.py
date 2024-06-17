# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_cdk import (
    aws_kms as kms
)


def create_kms_keys(scope) -> dict:
    """
    Create KMS keys and return a dictionary of keys.
    
    This function creates KMS keys for SNS topics and Lambda functions
    and returns a dictionary with the created keys.
    
    Args:
        scope (Construct): The scope in which to define this construct's resources.

    Returns:
        dict: A dictionary containing the created KMS keys (IKey).
    """
    i_kms_keys = {}

    # SNS Topic KMS Key
    i_sns_key = kms.Key(
        scope, "rSnsTopicKmsKey",
        enable_key_rotation=True
    )
    i_sns_key.add_alias("alias/accountcreation/kms/snstopic/key")
    i_kms_keys['SNS'] = i_sns_key

    # Lambda KMS Key
    i_sns_key = kms.Key(
        scope, "rLambdaKmsKey",
        enable_key_rotation=True
    )
    i_sns_key.add_alias("alias/accountcreation/kms/lambda/key")
    i_kms_keys['Lambda'] = i_sns_key

    return i_kms_keys
