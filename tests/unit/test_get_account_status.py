# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import importlib.util
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

# Add lambda layer and lambda source to path for helper imports
sys.path.insert(0, 'app/lambda_layer/account_creation_helper/python')
sys.path.insert(0, 'app/lambda_src/stepfunction/GetAccountStatus')

# Set environment variables required before module import (module-level boto3 client)
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_LAMBDA_FUNCTION_NAME", "test-function")
os.environ.setdefault("LZA_CODEPIPELINE_NAME", "test-pipeline")

_spec = importlib.util.spec_from_file_location(
    "get_account_status_main",
    "app/lambda_src/stepfunction/GetAccountStatus/main.py"
)
get_status_main = importlib.util.module_from_spec(_spec)
sys.modules["get_account_status_main"] = get_status_main
_spec.loader.exec_module(get_status_main)


class TestGetAccountStatusPipelineSucceeded:
    """Test: provisioned product complete after pipeline succeeds."""

    @patch.object(get_status_main, 'get_service_catalog_info')
    @patch.object(get_status_main, 'HelperCodePipeline')
    def test_pipeline_succeeded_returns_success(
        self, mock_pipeline_cls, mock_get_sc_info, monkeypatch
    ):
        """When pipeline succeeds, Account.Status is SUCCESS with SC outputs."""
        monkeypatch.setenv("LZA_CODEPIPELINE_NAME", "test-pipeline")

        mock_pipeline = MagicMock()
        mock_pipeline.status.return_value = "Succeeded"
        mock_pipeline_cls.return_value = mock_pipeline

        mock_get_sc_info.return_value = {
            "AccountId": "123456789012",
            "ProvisionedProductId": "pp-abc123",
            "ProvisionedProductName": "test-account"
        }

        event = {
            "Payload": {
                "AccountInfo": {
                    "AccountName": "test-account",
                    "BypassCreation": "false"
                },
                "CodePipeline": {
                    "CodePipelineExecutionId": "exec-123"
                }
            }
        }

        result = get_status_main.lambda_handler(event, None)

        assert result['Account']['Status'] == "SUCCESS"
        assert result['Account']['Outputs']['AccountId'] == "123456789012"
        assert result['CodePipeline']['CodePipelineRunStatus'] == "Succeeded"


class TestGetAccountStatusPipelineInProgress:
    """Test: pipeline still running returns UNDER_CHANGE."""

    @patch.object(get_status_main, 'HelperCodePipeline')
    def test_pipeline_in_progress_returns_under_change(
        self, mock_pipeline_cls, monkeypatch
    ):
        """When pipeline is InProgress, Account.Status is UNDER_CHANGE."""
        monkeypatch.setenv("LZA_CODEPIPELINE_NAME", "test-pipeline")

        mock_pipeline = MagicMock()
        mock_pipeline.status.return_value = "InProgress"
        mock_pipeline_cls.return_value = mock_pipeline

        event = {
            "Payload": {
                "AccountInfo": {
                    "AccountName": "test-account",
                    "BypassCreation": "false"
                },
                "CodePipeline": {
                    "CodePipelineExecutionId": "exec-123"
                }
            }
        }

        result = get_status_main.lambda_handler(event, None)

        assert result['Account']['Status'] == "UNDER_CHANGE"
        assert result['CodePipeline']['CodePipelineRunStatus'] == "InProgress"


class TestGetAccountStatusPipelineFailed:
    """Test: provisioned product failed."""

    @patch.object(get_status_main, 'HelperCodeBuild')
    @patch.object(get_status_main, 'HelperCodePipeline')
    def test_pipeline_failed_raises_runtime_error(
        self, mock_pipeline_cls, mock_codebuild_cls, monkeypatch
    ):
        """When pipeline fails, RuntimeError is raised with error details."""
        monkeypatch.setenv("LZA_CODEPIPELINE_NAME", "test-pipeline")

        mock_pipeline = MagicMock()
        mock_pipeline.status.return_value = "Failed"
        mock_pipeline.get_failed_action.return_value = {
            "actionName": "BuildAction",
            "stageName": "Build",
            "output": {
                "executionResult": {
                    "externalExecutionId": "build-123"
                }
            },
            "input": {
                "actionTypeId": {
                    "provider": "CodeBuild"
                }
            }
        }
        mock_pipeline_cls.return_value = mock_pipeline

        mock_codebuild = MagicMock()
        mock_codebuild.get_failed_phase_info.return_value = {
            "phaseName": "BUILD",
            "phaseStatus": "FAILED"
        }
        mock_codebuild_cls.return_value = mock_codebuild

        event = {
            "Payload": {
                "AccountInfo": {
                    "AccountName": "test-account",
                    "BypassCreation": "false"
                },
                "CodePipeline": {
                    "CodePipelineExecutionId": "exec-123"
                }
            }
        }

        with pytest.raises(RuntimeError):
            get_status_main.lambda_handler(event, None)


class TestGetAccountStatusBypassCreation:
    """Test: bypass creation skips pipeline check."""

    @patch.object(get_status_main, 'get_service_catalog_info')
    def test_bypass_creation_returns_bypassed(
        self, mock_get_sc_info, monkeypatch
    ):
        """When BypassCreation is true, Account.Status is BYPASSED."""
        monkeypatch.setenv("LZA_CODEPIPELINE_NAME", "test-pipeline")

        mock_get_sc_info.return_value = {
            "AccountId": "123456789012",
            "ProvisionedProductId": "pp-abc123",
            "ProvisionedProductName": "test-account"
        }

        event = {
            "Payload": {
                "AccountInfo": {
                    "AccountName": "test-account",
                    "BypassCreation": "true"
                },
                "CodePipeline": {
                    "CodePipelineExecutionId": "exec-123"
                }
            }
        }

        result = get_status_main.lambda_handler(event, None)

        assert result['Account']['Status'] == "BYPASSED"
        assert result['Account']['Outputs']['AccountId'] == "123456789012"


class TestGetAccountStatusMissingFields:
    """Test: missing required fields raises RuntimeError."""

    def test_missing_payload_key_raises_error(self, monkeypatch):
        """When 'Payload' key is missing from event, KeyError is raised."""
        monkeypatch.setenv("LZA_CODEPIPELINE_NAME", "test-pipeline")

        event = {"SomeOtherKey": "value"}

        with pytest.raises(KeyError):
            get_status_main.lambda_handler(event, None)

    def test_missing_account_info_raises_runtime_error(self, monkeypatch):
        """When AccountInfo is missing, RuntimeError is raised."""
        monkeypatch.setenv("LZA_CODEPIPELINE_NAME", "test-pipeline")

        event = {
            "Payload": {
                "CodePipeline": {
                    "CodePipelineExecutionId": "exec-123"
                }
            }
        }

        with pytest.raises(RuntimeError):
            get_status_main.lambda_handler(event, None)


class TestGetAccountStatusPipelineStopped:
    """Test: pipeline in unexpected status raises error."""

    @patch.object(get_status_main, 'HelperCodePipeline')
    def test_pipeline_stopped_raises_runtime_error(
        self, mock_pipeline_cls, monkeypatch
    ):
        """When pipeline is Stopped, RuntimeError is raised."""
        monkeypatch.setenv("LZA_CODEPIPELINE_NAME", "test-pipeline")

        mock_pipeline = MagicMock()
        mock_pipeline.status.return_value = "Stopped"
        mock_pipeline_cls.return_value = mock_pipeline

        event = {
            "Payload": {
                "AccountInfo": {
                    "AccountName": "test-account",
                    "BypassCreation": "false"
                },
                "CodePipeline": {
                    "CodePipelineExecutionId": "exec-123"
                }
            }
        }

        with pytest.raises(RuntimeError):
            get_status_main.lambda_handler(event, None)
