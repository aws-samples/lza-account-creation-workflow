# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0


import boto3

from app.lambda_src.stepfunction.CreateAccount.helper import HelperCodePipeline
from moto import mock_codepipeline
from moto.core import DEFAULT_ACCOUNT_ID


def test_instantiate_helper(aws_credentials):
    with mock_codepipeline():
        cph = HelperCodePipeline(
            "AWSAccelerator-Pipeline", boto3.client("codepipeline")
        )
        assert cph.pipeline_name == "AWSAccelerator-Pipeline"


# Cannot test start_execution or other_running_executions with moto as they have
# not yet been implemented. Will have to use Stubber
