# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_cdk import (
    aws_kms as kms
)


def create_kms_keys(scope) -> dict:
    i_kms_keys = {}

    # SNS Topic KMS Key
    i_sns_key = kms.Key(
        scope, f"rSnsTopicKmsKey",
        enable_key_rotation=True
    )
    i_sns_key.add_alias("alias/accountcreation/kms/snstopic/key")
    i_kms_keys['SNS'] = i_sns_key

    # Lambda KMS Key
    i_sns_key = kms.Key(
        scope, f"rLambdaKmsKey",
        enable_key_rotation=True
    )
    i_sns_key.add_alias("alias/accountcreation/kms/lambda/key")
    i_kms_keys['Lambda'] = i_sns_key

    return i_kms_keys