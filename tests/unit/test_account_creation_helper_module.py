# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import sys
from datetime import datetime
from unittest.mock import patch, MagicMock

import boto3
import botocore
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from moto import mock_aws
import pytest

sys.path.insert(0, 'app/lambda_layer/account_creation_helper/python')


class TestAssumeRoleArn:
    """Test assume_role_arn calls STS correctly."""

    @mock_aws
    def test_assume_role_returns_credentials(self, aws_credentials):
        """assume_role_arn returns dict with access key, secret, and token."""
        from account_creation_helper import assume_role_arn
        import account_creation_helper

        # Reset module-level STS client to use moto mock
        account_creation_helper.STS_CLIENT = boto3.client('sts')

        result = assume_role_arn(
            role_arn="arn:aws:iam::123456789012:role/TestRole",
            role_session_name="test-session"
        )

        assert "aws_access_key_id" in result
        assert "aws_secret_access_key" in result
        assert "aws_session_token" in result
        assert result["aws_access_key_id"] is not None
        assert result["aws_secret_access_key"] is not None
        assert result["aws_session_token"] is not None

    @mock_aws
    def test_assume_role_uses_default_session_name(self, aws_credentials, monkeypatch):
        """assume_role_arn uses Lambda function name as default session name."""
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "my-lambda-func")

        from account_creation_helper import assume_role_arn
        import account_creation_helper

        account_creation_helper.STS_CLIENT = boto3.client('sts')

        result = assume_role_arn(
            role_arn="arn:aws:iam::123456789012:role/TestRole"
        )

        assert "aws_access_key_id" in result


class TestHelperCodePipelineOtherRunningExecutions:
    """Test HelperCodePipeline.other_running_executions."""

    def test_returns_empty_list_when_none_running(self, aws_credentials):
        """Returns empty list when no InProgress pipeline executions exist."""
        codepipeline_client = botocore.session.get_session().create_client(
            "codepipeline", region_name="us-east-1"
        )
        stubber = Stubber(codepipeline_client)

        stubber.add_response(
            "list_pipeline_executions",
            {
                "pipelineExecutionSummaries": [
                    {
                        "pipelineExecutionId": "exec-1",
                        "status": "Succeeded",
                        "startTime": datetime(2024, 1, 1),
                        "lastUpdateTime": datetime(2024, 1, 1),
                    },
                    {
                        "pipelineExecutionId": "exec-2",
                        "status": "Failed",
                        "startTime": datetime(2024, 1, 2),
                        "lastUpdateTime": datetime(2024, 1, 2),
                    },
                ]
            },
            {"pipelineName": "test-pipeline"},
        )
        stubber.activate()

        from account_creation_helper import HelperCodePipeline

        pipeline = HelperCodePipeline(pipeline_name="test-pipeline")
        pipeline.cp_client = codepipeline_client

        result = pipeline.other_running_executions()

        assert result == []
        stubber.deactivate()

    def test_returns_running_executions(self, aws_credentials):
        """Returns list of InProgress executions when some are running."""
        codepipeline_client = botocore.session.get_session().create_client(
            "codepipeline", region_name="us-east-1"
        )
        stubber = Stubber(codepipeline_client)

        stubber.add_response(
            "list_pipeline_executions",
            {
                "pipelineExecutionSummaries": [
                    {
                        "pipelineExecutionId": "exec-running",
                        "status": "InProgress",
                        "startTime": datetime(2024, 1, 1),
                        "lastUpdateTime": datetime(2024, 1, 1),
                    },
                    {
                        "pipelineExecutionId": "exec-done",
                        "status": "Succeeded",
                        "startTime": datetime(2024, 1, 2),
                        "lastUpdateTime": datetime(2024, 1, 2),
                    },
                ]
            },
            {"pipelineName": "test-pipeline"},
        )
        stubber.activate()

        from account_creation_helper import HelperCodePipeline

        pipeline = HelperCodePipeline(pipeline_name="test-pipeline")
        pipeline.cp_client = codepipeline_client

        result = pipeline.other_running_executions()

        assert len(result) == 1
        assert result[0]["pipelineExecutionId"] == "exec-running"
        stubber.deactivate()


class TestHelperCodePipelineStatus:
    """Test HelperCodePipeline.status retries on PipelineExecutionNotFoundException."""

    def test_status_returns_on_success(self, aws_credentials):
        """Returns status string when pipeline execution is found."""
        codepipeline_client = botocore.session.get_session().create_client(
            "codepipeline", region_name="us-east-1"
        )
        stubber = Stubber(codepipeline_client)

        stubber.add_response(
            "get_pipeline_execution",
            {
                "pipelineExecution": {
                    "pipelineName": "test-pipeline",
                    "pipelineVersion": 1,
                    "status": "Succeeded",
                    "artifactRevisions": [],
                }
            },
            {
                "pipelineName": "test-pipeline",
                "pipelineExecutionId": "exec-123",
            },
        )
        stubber.activate()

        from account_creation_helper import HelperCodePipeline

        pipeline = HelperCodePipeline(pipeline_name="test-pipeline")
        pipeline.cp_client = codepipeline_client

        result = pipeline.status(execution_id="exec-123")

        assert result == "Succeeded"
        stubber.deactivate()

    @patch('account_creation_helper.time.sleep', return_value=None)
    def test_status_retries_then_raises(self, mock_sleep, aws_credentials):
        """Retries up to max_attempts then raises the exception."""
        from account_creation_helper import HelperCodePipeline

        pipeline = HelperCodePipeline(pipeline_name="test-pipeline")

        # Mock cp_client to always raise PipelineExecutionNotFoundException
        mock_client = MagicMock()
        mock_exception = type(
            'PipelineExecutionNotFoundException',
            (Exception,),
            {}
        )
        mock_client.exceptions.PipelineExecutionNotFoundException = mock_exception
        mock_client.get_pipeline_execution.side_effect = mock_exception(
            "Pipeline execution not found"
        )
        pipeline.cp_client = mock_client

        with pytest.raises(mock_exception):
            pipeline.status(execution_id="nonexistent-exec", max_attempts=2)

        # initial call + 2 retries = 3 total calls
        assert mock_client.get_pipeline_execution.call_count == 3


class TestDecommissionProcessRunning:
    """Test decommission_process_running function."""

    def test_returns_empty_when_project_not_found(self, aws_credentials):
        """Returns empty list when CodeBuild project does not exist."""
        codebuild_client = botocore.session.get_session().create_client(
            "codebuild", region_name="us-east-1"
        )
        stubber = Stubber(codebuild_client)

        stubber.add_client_error(
            "list_builds_for_project",
            service_error_code="ResourceNotFoundException",
            service_message="Project not found",
            expected_params={"projectName": "nonexistent-project"},
        )
        stubber.activate()

        from account_creation_helper import decommission_process_running

        result = decommission_process_running(
            project_name="nonexistent-project",
            cb_client=codebuild_client
        )

        assert result == []
        stubber.deactivate()

    def test_returns_in_progress_builds(self, aws_credentials):
        """Returns list of IN_PROGRESS builds when project has running builds."""
        codebuild_client = botocore.session.get_session().create_client(
            "codebuild", region_name="us-east-1"
        )
        stubber = Stubber(codebuild_client)

        stubber.add_response(
            "list_builds_for_project",
            {"ids": ["build-1", "build-2"]},
            {"projectName": "lzac-account-decommission"},
        )
        stubber.add_response(
            "batch_get_builds",
            {
                "builds": [
                    {
                        "id": "build-1",
                        "arn": "arn:aws:codebuild:us-east-1:123:build/build-1",
                        "buildNumber": 1,
                        "startTime": datetime(2024, 1, 1),
                        "currentPhase": "BUILD",
                        "buildStatus": "IN_PROGRESS",
                        "projectName": "lzac-account-decommission",
                    },
                    {
                        "id": "build-2",
                        "arn": "arn:aws:codebuild:us-east-1:123:build/build-2",
                        "buildNumber": 2,
                        "startTime": datetime(2024, 1, 1),
                        "endTime": datetime(2024, 1, 1),
                        "currentPhase": "COMPLETED",
                        "buildStatus": "SUCCEEDED",
                        "projectName": "lzac-account-decommission",
                    },
                ]
            },
            {"ids": ["build-1", "build-2"]},
        )
        stubber.activate()

        from account_creation_helper import decommission_process_running

        result = decommission_process_running(
            project_name="lzac-account-decommission",
            cb_client=codebuild_client
        )

        assert len(result) == 1
        assert result[0]["id"] == "build-1"
        assert result[0]["buildStatus"] == "IN_PROGRESS"
        stubber.deactivate()


class TestPipelineRunning:
    """Test pipeline_running function."""

    @patch('account_creation_helper.boto3.client')
    def test_returns_empty_when_pipeline_not_found(
        self, mock_boto_client, aws_credentials
    ):
        """Returns empty list when PipelineNotFoundException is raised."""
        mock_cp_client = MagicMock()
        mock_boto_client.return_value = mock_cp_client

        mock_paginator = MagicMock()
        mock_cp_client.get_paginator.return_value = mock_paginator

        # Simulate PipelineNotFoundException via paginator search
        error_response = {
            'Error': {
                'Code': 'PipelineNotFoundException',
                'Message': 'Pipeline not found'
            }
        }
        mock_paginator.paginate.return_value.search.side_effect = ClientError(
            error_response, 'ListPipelineExecutions'
        )

        from account_creation_helper import pipeline_running

        result = pipeline_running(pipeline_name="nonexistent-pipeline")

        assert result == []

    @patch('account_creation_helper.boto3.client')
    def test_returns_empty_list_when_no_running(
        self, mock_boto_client, aws_credentials
    ):
        """Returns empty list when no InProgress pipeline executions exist."""
        mock_cp_client = MagicMock()
        mock_boto_client.return_value = mock_cp_client

        mock_paginator = MagicMock()
        mock_cp_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value.search.return_value = iter([])

        from account_creation_helper import pipeline_running

        result = pipeline_running(pipeline_name="my-pipeline")

        assert result == []

    @patch('account_creation_helper.boto3.client')
    def test_returns_running_executions(self, mock_boto_client, aws_credentials):
        """Returns list of InProgress executions when pipeline is running."""
        mock_cp_client = MagicMock()
        mock_boto_client.return_value = mock_cp_client

        mock_paginator = MagicMock()
        mock_cp_client.get_paginator.return_value = mock_paginator

        running_execution = {
            "pipelineExecutionId": "exec-running-123",
            "status": "InProgress",
            "startTime": datetime(2024, 6, 1),
            "lastUpdateTime": datetime(2024, 6, 1),
        }
        mock_paginator.paginate.return_value.search.return_value = iter(
            [running_execution]
        )

        from account_creation_helper import pipeline_running

        result = pipeline_running(pipeline_name="my-lza-pipeline")

        assert len(result) == 1
        assert result[0]["pipelineExecutionId"] == "exec-running-123"
        assert result[0]["status"] == "InProgress"
