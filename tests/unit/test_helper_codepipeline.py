# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0


import boto3

from app.lambda_layer.account_creation_helper.python.account_creation_helper import (
    HelperCodePipeline
)
from moto import mock_aws
from moto.core import DEFAULT_ACCOUNT_ID


def test_instantiate_helper(aws_credentials):
    with mock_aws():
        cph = HelperCodePipeline("AWSAccelerator-Pipeline")
        cph.cp_client = boto3.client("codepipeline")
        assert cph.pipeline_name == "AWSAccelerator-Pipeline"


# Cannot test start_execution or other_running_executions with moto as they have
# not yet been implemented. Will have to use Stubber
