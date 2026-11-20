# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import importlib.util
import json
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

# Set environment variables required before module import (module-level boto3 client)
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_LAMBDA_FUNCTION_NAME", "test-function")
os.environ.setdefault("SNS_FAILURE_TOPIC", "arn:aws:sns:us-east-1:123456789012:test-topic")

# Add lambda layer to path
sys.path.insert(0, 'app/lambda_layer/account_creation_helper/python')

# Load the local helper module with a unique name to avoid collision
_helper_spec = importlib.util.spec_from_file_location(
    "return_response_helper",
    "app/lambda_src/stepfunction/ReturnResponse/helper.py"
)
_helper_mod = importlib.util.module_from_spec(_helper_spec)
_helper_spec.loader.exec_module(_helper_mod)

# Inject the helper into sys.modules so the main module picks it up
_original_helper = sys.modules.get("helper")
sys.modules["helper"] = _helper_mod

_spec = importlib.util.spec_from_file_location(
    "return_response_main",
    "app/lambda_src/stepfunction/ReturnResponse/main.py"
)
return_response_main = importlib.util.module_from_spec(_spec)
sys.modules["return_response_main"] = return_response_main
_spec.loader.exec_module(return_response_main)

# Restore original helper module
if _original_helper is not None:
    sys.modules["helper"] = _original_helper
else:
    sys.modules.pop("helper", None)


class TestReturnResponseSuccess:
    """Test: success path returns account number."""

    def test_success_returns_account_id(self, monkeypatch):
        """When no error in StageInput, returns AccountId string."""
        monkeypatch.setenv("SNS_FAILURE_TOPIC", "arn:aws:sns:us-east-1:123456789012:test-topic")

        event = {
            "StageInput": {
                "Payload": {
                    "Account": {
                        "Outputs": {
                            "AccountId": "987654321098"
                        }
                    }
                }
            },
            "OriginalInput": {
                "AccountInfo": {
                    "AccountName": "test-account"
                }
            }
        }

        result = return_response_main.lambda_handler(event, None)

        assert result == "987654321098"


class TestReturnResponseFailure:
    """Test: failure path publishes to SNS and raises exception."""

    @patch.object(return_response_main, 'send_sns_message')
    def test_error_sends_sns_and_raises(
        self, mock_send_sns, monkeypatch
    ):
        """When Error is in StageInput, sends SNS and raises exception."""
        monkeypatch.setenv("SNS_FAILURE_TOPIC", "arn:aws:sns:us-east-1:123456789012:test-topic")

        error_cause = json.dumps({
            "errorMessage": "The account creation failed due to quota limit",
            "errorType": "RuntimeError"
        })

        event = {
            "StageInput": {
                "Error": "RuntimeError",
                "Cause": error_cause
            },
            "OriginalInput": {
                "AccountInfo": {
                    "AccountName": "failed-account"
                }
            }
        }

        with pytest.raises(return_response_main.StepFunctionTaskFailureException):
            return_response_main.lambda_handler(event, None)

        mock_send_sns.assert_called_once_with(
            error="The account creation failed due to quota limit",
            account_name="failed-account"
        )


class TestReturnResponseSnsPublishFailure:
    """Test: error handling for SNS publish failure."""

    @patch.object(return_response_main, 'send_sns_message')
    def test_sns_client_error_raises_runtime_error(
        self, mock_send_sns, monkeypatch
    ):
        """When send_sns_message raises ClientError, RuntimeError is raised."""
        from botocore.exceptions import ClientError

        monkeypatch.setenv("SNS_FAILURE_TOPIC", "arn:aws:sns:us-east-1:123456789012:test-topic")

        mock_send_sns.side_effect = ClientError(
            {"Error": {"Code": "NotFound", "Message": "Topic not found"}},
            "Publish"
        )

        error_cause = json.dumps({
            "errorMessage": "Some failure occurred",
            "errorType": "RuntimeError"
        })

        event = {
            "StageInput": {
                "Error": "RuntimeError",
                "Cause": error_cause
            },
            "OriginalInput": {
                "AccountInfo": {
                    "AccountName": "failed-account"
                }
            }
        }

        with pytest.raises(RuntimeError):
            return_response_main.lambda_handler(event, None)


class TestReturnResponseMissingFields:
    """Test: missing required fields in event."""

    def test_missing_stage_input_raises_runtime_error(self, monkeypatch):
        """When StageInput is missing, RuntimeError is raised."""
        monkeypatch.setenv("SNS_FAILURE_TOPIC", "arn:aws:sns:us-east-1:123456789012:test-topic")

        event = {"SomeOtherKey": "value"}

        with pytest.raises(RuntimeError):
            return_response_main.lambda_handler(event, None)

    def test_malformed_cause_json_raises_runtime_error(self, monkeypatch):
        """When Cause is not valid JSON, RuntimeError is raised."""
        monkeypatch.setenv("SNS_FAILURE_TOPIC", "arn:aws:sns:us-east-1:123456789012:test-topic")

        event = {
            "StageInput": {
                "Error": "RuntimeError",
                "Cause": "this is not valid json"
            },
            "OriginalInput": {
                "AccountInfo": {
                    "AccountName": "failed-account"
                }
            }
        }

        with pytest.raises(RuntimeError):
            return_response_main.lambda_handler(event, None)
