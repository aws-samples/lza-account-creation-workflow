# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import importlib.util
import sys

import pytest

sys.path.insert(0, 'app/lambda_layer/account_creation_helper/python')

# Import with a unique module name to avoid collision with other Lambda
# main.py modules (e.g., CreateAccountGitHub, GetExecutionStatus)
_spec = importlib.util.spec_from_file_location(
    "check_for_running_processes_main",
    "app/lambda_src/stepfunction/CheckForRunningProcesses/main.py"
)
check_running_main = importlib.util.module_from_spec(_spec)
sys.modules["check_for_running_processes_main"] = check_running_main
_spec.loader.exec_module(check_running_main)


from unittest.mock import patch


class TestCheckForRunningProcessesHappyPath:
    """Test happy path: no running processes returns empty dict."""

    @patch.object(check_running_main, 'pipeline_running', return_value=[])
    @patch.object(check_running_main, 'decommission_process_running', return_value=[])
    def test_no_running_processes(
        self, mock_decommission, mock_pipeline, monkeypatch
    ):
        """When no processes are running, CheckForRunningProcesses is empty."""
        monkeypatch.setenv("ACCOUNT_DECOMMISSION_PROJECT_NAME", "test-project")
        monkeypatch.setenv("LZA_PIPELINE_NAME", "test-pipeline")

        event = {
            "AccountInfo": {
                "AccountName": "test-account",
                "ManagedOrganizationalUnit": "Workloads",
                "SupportDL": "test@example.com",
                "ForceUpdate": "false"
            }
        }

        result = check_running_main.lambda_handler(event, None)

        assert result['CheckForRunningProcesses'] == {}
        assert result['AccountInfo'] == event['AccountInfo']
        assert result['ForceUpdate'] == 'false'


class TestCheckForRunningProcessesCodeBuild:
    """Test running CodeBuild returns project name in payload."""

    @patch.object(check_running_main, 'pipeline_running', return_value=[])
    @patch.object(
        check_running_main, 'decommission_process_running',
        return_value=[{"id": "build-1", "buildStatus": "IN_PROGRESS"}]
    )
    def test_running_codebuild(
        self, mock_decommission, mock_pipeline, monkeypatch
    ):
        """When CodeBuild is running, project name appears in payload."""
        monkeypatch.setenv("ACCOUNT_DECOMMISSION_PROJECT_NAME", "my-decommission-project")
        monkeypatch.setenv("LZA_PIPELINE_NAME", "test-pipeline")

        event = {
            "AccountInfo": {
                "AccountName": "test-account",
                "ManagedOrganizationalUnit": "Workloads",
                "SupportDL": "test@example.com"
            }
        }

        result = check_running_main.lambda_handler(event, None)

        assert result['CheckForRunningProcesses']['CodeBuild'] == "my-decommission-project"


class TestCheckForRunningProcessesCodePipeline:
    """Test running CodePipeline returns pipeline name in payload."""

    @patch.object(
        check_running_main, 'pipeline_running',
        return_value=[{"pipelineExecutionId": "exec-1", "status": "InProgress"}]
    )
    @patch.object(check_running_main, 'decommission_process_running', return_value=[])
    def test_running_codepipeline(
        self, mock_decommission, mock_pipeline, monkeypatch
    ):
        """When CodePipeline is running, pipeline name appears in payload."""
        monkeypatch.setenv("ACCOUNT_DECOMMISSION_PROJECT_NAME", "test-project")
        monkeypatch.setenv("LZA_PIPELINE_NAME", "my-lza-pipeline")

        event = {
            "AccountInfo": {
                "AccountName": "test-account",
                "ManagedOrganizationalUnit": "Workloads",
                "SupportDL": "test@example.com"
            }
        }

        result = check_running_main.lambda_handler(event, None)

        assert result['CheckForRunningProcesses']['CodePipeline'] == "my-lza-pipeline"


class TestCheckForRunningProcessesMissingKey:
    """Test missing AccountInfo key raises RuntimeError."""

    @patch.object(check_running_main, 'pipeline_running', return_value=[])
    @patch.object(check_running_main, 'decommission_process_running', return_value=[])
    def test_missing_account_info_raises_error(
        self, mock_decommission, mock_pipeline, monkeypatch
    ):
        """When AccountInfo is missing from event, RuntimeError is raised."""
        monkeypatch.setenv("ACCOUNT_DECOMMISSION_PROJECT_NAME", "test-project")
        monkeypatch.setenv("LZA_PIPELINE_NAME", "test-pipeline")

        event = {"SomeOtherKey": "value"}

        with pytest.raises(RuntimeError, match="Missing required key"):
            check_running_main.lambda_handler(event, None)


class TestCheckForRunningProcessesRetryPayload:
    """Test nested Payload.AccountInfo structure (retry case)."""

    @patch.object(check_running_main, 'pipeline_running', return_value=[])
    @patch.object(check_running_main, 'decommission_process_running', return_value=[])
    def test_nested_payload_structure(
        self, mock_decommission, mock_pipeline, monkeypatch
    ):
        """When event has Payload wrapper (retry), AccountInfo is extracted."""
        monkeypatch.setenv("ACCOUNT_DECOMMISSION_PROJECT_NAME", "test-project")
        monkeypatch.setenv("LZA_PIPELINE_NAME", "test-pipeline")

        event = {
            "Payload": {
                "AccountInfo": {
                    "AccountName": "retry-account",
                    "ManagedOrganizationalUnit": "Workloads",
                    "SupportDL": "test@example.com",
                    "ForceUpdate": "true"
                }
            }
        }

        result = check_running_main.lambda_handler(event, None)

        assert result['AccountInfo']['AccountName'] == "retry-account"
        assert result['CheckForRunningProcesses'] == {}


class TestCheckForRunningProcessesForceUpdate:
    """Test ForceUpdate passed through correctly."""

    @patch.object(check_running_main, 'pipeline_running', return_value=[])
    @patch.object(check_running_main, 'decommission_process_running', return_value=[])
    def test_force_update_true(
        self, mock_decommission, mock_pipeline, monkeypatch
    ):
        """ForceUpdate value from AccountInfo is passed through to payload."""
        monkeypatch.setenv("ACCOUNT_DECOMMISSION_PROJECT_NAME", "test-project")
        monkeypatch.setenv("LZA_PIPELINE_NAME", "test-pipeline")

        event = {
            "AccountInfo": {
                "AccountName": "test-account",
                "ManagedOrganizationalUnit": "Workloads",
                "SupportDL": "test@example.com",
                "ForceUpdate": "true"
            }
        }

        result = check_running_main.lambda_handler(event, None)

        assert result['ForceUpdate'] == 'true'

    @patch.object(check_running_main, 'pipeline_running', return_value=[])
    @patch.object(check_running_main, 'decommission_process_running', return_value=[])
    def test_force_update_default_false(
        self, mock_decommission, mock_pipeline, monkeypatch
    ):
        """ForceUpdate defaults to 'false' when not present in AccountInfo."""
        monkeypatch.setenv("ACCOUNT_DECOMMISSION_PROJECT_NAME", "test-project")
        monkeypatch.setenv("LZA_PIPELINE_NAME", "test-pipeline")

        event = {
            "AccountInfo": {
                "AccountName": "test-account",
                "ManagedOrganizationalUnit": "Workloads",
                "SupportDL": "test@example.com"
            }
        }

        result = check_running_main.lambda_handler(event, None)

        assert result['ForceUpdate'] == 'false'
