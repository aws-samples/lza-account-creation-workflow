# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import sys
import json
import importlib.util
from unittest.mock import patch, MagicMock

import pytest
from botocore.exceptions import ClientError

# Set region before importing module (module-level boto3 clients need it)
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault(
    "SF_EXECUTION_ARN_BASE",
    "arn:aws:states:us-east-1:123456789012:execution:test-sf"
)

# Import with unique module name to avoid conflicts with other test files
_spec = importlib.util.spec_from_file_location(
    "get_execution_status_main",
    "app/lambda_src/api/GetExecutionStatus/main.py"
)
get_execution_status_main = importlib.util.module_from_spec(_spec)
sys.modules["get_execution_status_main"] = get_execution_status_main
_spec.loader.exec_module(get_execution_status_main)

lambda_handler = get_execution_status_main.lambda_handler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def aws_credentials(monkeypatch):
    """Mocked AWS creds for tests"""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def env_vars(monkeypatch):
    """Set required environment variables for GetExecutionStatus"""
    monkeypatch.setenv(
        "SF_EXECUTION_ARN_BASE",
        "arn:aws:states:us-east-1:123456789012:execution:test-sf"
    )


@pytest.fixture
def api_event():
    """Helper to build API Gateway event with query parameters"""
    def _make_event(execution_arn=None, execution=None):
        params = {}
        if execution_arn:
            params["execution_arn"] = execution_arn
        if execution:
            params["execution"] = execution
        return {
            "queryStringParameters": params if params else None
        }
    return _make_event


# ---------------------------------------------------------------------------
# Tests: Missing Parameters
# ---------------------------------------------------------------------------


class TestGetExecutionStatusValidation:
    """Tests for input validation"""

    def test_missing_both_params_returns_400(
        self, aws_credentials, env_vars, api_event
    ):
        """Missing both execution_arn and execution returns 400"""
        event = api_event()
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"]["code"] == "MISSING_PARAMETER"
        assert "execution_arn" in body["error"]["message"]

    def test_empty_query_params_returns_400(
        self, aws_credentials, env_vars
    ):
        """Empty queryStringParameters returns 400"""
        event = {"queryStringParameters": {}}
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400

    def test_null_query_params_returns_400(
        self, aws_credentials, env_vars
    ):
        """Null queryStringParameters returns 400"""
        event = {"queryStringParameters": None}
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400


# ---------------------------------------------------------------------------
# Tests: Successful Status Retrieval
# ---------------------------------------------------------------------------


class TestGetExecutionStatusSuccess:
    """Tests for successful execution status retrieval"""

    @patch("get_execution_status_main.SF_CLIENT")
    def test_succeeded_execution_returns_status(
        self, mock_sf, aws_credentials, env_vars, api_event
    ):
        """Succeeded execution returns status without current task"""
        mock_sf.describe_execution.return_value = {
            "status": "SUCCEEDED"
        }
        mock_sf.exceptions = MagicMock()
        mock_sf.exceptions.ExecutionDoesNotExist = type(
            "ExecutionDoesNotExist", (Exception,), {}
        )

        event = api_event(
            execution_arn="arn:aws:states:us-east-1:123456789012:execution:test-sf:exec-123"
        )
        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["Status"] == "SUCCEEDED"
        assert "CurrentExecutionTask" not in body

    @patch("get_execution_status_main.SF_CLIENT")
    def test_running_execution_returns_current_task(
        self, mock_sf, aws_credentials, env_vars, api_event
    ):
        """Running execution returns status with current task name"""
        mock_sf.describe_execution.return_value = {
            "status": "RUNNING"
        }
        mock_sf.get_execution_history.return_value = {
            "events": [
                {
                    "stateEnteredEventDetails": {
                        "name": "Wait 1 Minute (Wait for Account to Complete)"
                    }
                }
            ]
        }
        mock_sf.exceptions = MagicMock()
        mock_sf.exceptions.ExecutionDoesNotExist = type(
            "ExecutionDoesNotExist", (Exception,), {}
        )

        event = api_event(
            execution_arn="arn:aws:states:us-east-1:123456789012:execution:test-sf:exec-123"
        )
        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["Status"] == "RUNNING"
        assert body["CurrentExecutionTask"] == "Wait 1 Minute (Wait for Account to Complete)"

    @patch("get_execution_status_main.SF_CLIENT")
    def test_failed_execution_returns_cause(
        self, mock_sf, aws_credentials, env_vars, api_event
    ):
        """Failed execution returns status with cause"""
        mock_sf.describe_execution.return_value = {
            "status": "FAILED",
            "cause": "Lambda function raised an error"
        }
        mock_sf.exceptions = MagicMock()
        mock_sf.exceptions.ExecutionDoesNotExist = type(
            "ExecutionDoesNotExist", (Exception,), {}
        )

        event = api_event(
            execution_arn="arn:aws:states:us-east-1:123456789012:execution:test-sf:exec-123"
        )
        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["Status"] == "FAILED"
        assert body["Cause"] == "Lambda function raised an error"

    @patch("get_execution_status_main.SF_CLIENT")
    def test_execution_name_builds_arn_from_base(
        self, mock_sf, aws_credentials, env_vars, api_event
    ):
        """Using execution name (not ARN) constructs ARN from SF_EXECUTION_ARN_BASE"""
        mock_sf.describe_execution.return_value = {
            "status": "SUCCEEDED"
        }
        mock_sf.exceptions = MagicMock()
        mock_sf.exceptions.ExecutionDoesNotExist = type(
            "ExecutionDoesNotExist", (Exception,), {}
        )

        event = api_event(execution="my-execution-name")
        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        # Verify the constructed ARN was used
        mock_sf.describe_execution.assert_called_once_with(
            executionArn="arn:aws:states:us-east-1:123456789012:execution:test-sf:my-execution-name"
        )

    @patch("get_execution_status_main.SF_CLIENT")
    def test_running_execution_without_state_details(
        self, mock_sf, aws_credentials, env_vars, api_event
    ):
        """Running execution with no stateEnteredEventDetails returns fallback message"""
        mock_sf.describe_execution.return_value = {
            "status": "RUNNING"
        }
        mock_sf.get_execution_history.return_value = {
            "events": [
                {
                    # No stateEnteredEventDetails key
                    "type": "TaskScheduled"
                }
            ]
        }
        mock_sf.exceptions = MagicMock()
        mock_sf.exceptions.ExecutionDoesNotExist = type(
            "ExecutionDoesNotExist", (Exception,), {}
        )

        event = api_event(
            execution_arn="arn:aws:states:us-east-1:123456789012:execution:test-sf:exec-123"
        )
        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["Status"] == "RUNNING"
        # Falls back to .get('name') on the default dict
        assert "still starting" in body["CurrentExecutionTask"].lower()


# ---------------------------------------------------------------------------
# Tests: Execution Not Found
# ---------------------------------------------------------------------------


class TestGetExecutionStatusNotFound:
    """Tests for non-existent execution"""

    @patch("get_execution_status_main.SF_CLIENT")
    def test_nonexistent_execution_returns_404(
        self, mock_sf, aws_credentials, env_vars, api_event
    ):
        """Non-existent execution ARN returns 404"""
        not_found_exc = type("ExecutionDoesNotExist", (Exception,), {})
        mock_sf.exceptions.ExecutionDoesNotExist = not_found_exc
        mock_sf.describe_execution.side_effect = not_found_exc(
            "Execution does not exist"
        )

        event = api_event(
            execution_arn="arn:aws:states:us-east-1:123456789012:execution:test-sf:nonexistent"
        )
        response = lambda_handler(event, None)

        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert body["error"]["code"] == "NOT_FOUND"
        assert "not found" in body["error"]["message"].lower()

    @patch("get_execution_status_main.SF_CLIENT")
    def test_nonexistent_execution_name_returns_404(
        self, mock_sf, aws_credentials, env_vars, api_event
    ):
        """Non-existent execution name returns 404"""
        not_found_exc = type("ExecutionDoesNotExist", (Exception,), {})
        mock_sf.exceptions.ExecutionDoesNotExist = not_found_exc
        mock_sf.describe_execution.side_effect = not_found_exc(
            "Execution does not exist"
        )

        event = api_event(execution="does-not-exist-12345")
        response = lambda_handler(event, None)

        assert response["statusCode"] == 404


# ---------------------------------------------------------------------------
# Tests: Error Handling
# ---------------------------------------------------------------------------


class TestGetExecutionStatusErrors:
    """Tests for error handling"""

    @patch("get_execution_status_main.SF_CLIENT")
    def test_aws_client_error_returns_500(
        self, mock_sf, aws_credentials, env_vars, api_event
    ):
        """AWS ClientError returns 500"""
        mock_sf.exceptions = MagicMock()
        mock_sf.exceptions.ExecutionDoesNotExist = type(
            "ExecutionDoesNotExist", (Exception,), {}
        )
        mock_sf.describe_execution.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}},
            "DescribeExecution"
        )

        event = api_event(
            execution_arn="arn:aws:states:us-east-1:123456789012:execution:test-sf:exec-123"
        )
        response = lambda_handler(event, None)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["error"]["code"] == "AWS_ERROR"
        assert body["error"]["message"] == "Internal service error"

    @patch("get_execution_status_main.SF_CLIENT")
    def test_unexpected_error_returns_500(
        self, mock_sf, aws_credentials, env_vars, api_event
    ):
        """Unexpected exception returns 500"""
        mock_sf.exceptions = MagicMock()
        mock_sf.exceptions.ExecutionDoesNotExist = type(
            "ExecutionDoesNotExist", (Exception,), {}
        )
        mock_sf.describe_execution.side_effect = RuntimeError("unexpected boom")

        event = api_event(
            execution_arn="arn:aws:states:us-east-1:123456789012:execution:test-sf:exec-123"
        )
        response = lambda_handler(event, None)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["error"]["code"] == "INTERNAL_ERROR"
