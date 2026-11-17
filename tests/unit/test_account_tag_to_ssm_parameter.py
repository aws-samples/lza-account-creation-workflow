# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import importlib.util
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

# Set environment variables required before module import
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_LAMBDA_FUNCTION_NAME", "test-function")
os.environ.setdefault("ASSUMED_ROLE_NAME", "test-role")

# Add lambda layer to path
sys.path.insert(0, 'app/lambda_layer/account_creation_helper/python')

# Load the local helper module with a unique name to avoid collision
_helper_spec = importlib.util.spec_from_file_location(
    "account_tag_ssm_helper",
    "app/lambda_src/event/AccountTagToSsmParameter/helper.py"
)
_helper_mod = importlib.util.module_from_spec(_helper_spec)
_helper_spec.loader.exec_module(_helper_mod)

# Inject the helper into sys.modules so the main module picks it up
_original_helper = sys.modules.get("helper")
sys.modules["helper"] = _helper_mod

_spec = importlib.util.spec_from_file_location(
    "account_tag_to_ssm_parameter_main",
    "app/lambda_src/event/AccountTagToSsmParameter/main.py"
)
tag_ssm_main = importlib.util.module_from_spec(_spec)
sys.modules["account_tag_to_ssm_parameter_main"] = tag_ssm_main
_spec.loader.exec_module(tag_ssm_main)

# Restore original helper module
if _original_helper is not None:
    sys.modules["helper"] = _original_helper
else:
    sys.modules.pop("helper", None)


class TestAccountTagToSsmParameterTagResource:
    """Test happy path: TagResource event creates SSM parameters."""

    @patch.object(tag_ssm_main, 'create_ssm_parameters')
    @patch.object(tag_ssm_main, 'assume_role_arn')
    def test_tag_resource_creates_ssm_parameters(
        self, mock_assume_role, mock_create_ssm, monkeypatch
    ):
        """TagResource event assumes role and creates SSM parameters."""
        monkeypatch.setenv("ASSUMED_ROLE_NAME", "test-role")

        mock_assume_role.return_value = {
            "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "aws_session_token": "FwoGZXIvYXdzEA..."
        }

        event = {
            "detail": {
                "eventName": "TagResource",
                "requestParameters": {
                    "resourceId": "123456789012",
                    "tags": [
                        {"key": "Environment", "value": "Production"},
                        {"key": "Team:Name", "value": "Platform:Ops"}
                    ]
                }
            }
        }

        tag_ssm_main.lambda_handler(event, None)

        mock_assume_role.assert_called_once_with(
            role_arn="arn:aws:iam::123456789012:role/test-role"
        )
        mock_create_ssm.assert_called_once()
        call_kwargs = mock_create_ssm.call_args[1]
        # Colons in tag keys/values are replaced with dots
        assert call_kwargs['tags'] == [
            {"key": "Environment", "value": "Production"},
            {"key": "Team.Name", "value": "Platform.Ops"}
        ]


class TestAccountTagToSsmParameterUntagResource:
    """Test UntagResource event deletes SSM parameters."""

    @patch.object(tag_ssm_main, 'delete_ssm_parameters')
    @patch.object(tag_ssm_main, 'assume_role_arn')
    def test_untag_resource_deletes_ssm_parameters(
        self, mock_assume_role, mock_delete_ssm, monkeypatch
    ):
        """UntagResource event assumes role and deletes SSM parameters."""
        monkeypatch.setenv("ASSUMED_ROLE_NAME", "test-role")

        mock_assume_role.return_value = {
            "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "aws_session_token": "FwoGZXIvYXdzEA..."
        }

        event = {
            "detail": {
                "eventName": "UntagResource",
                "requestParameters": {
                    "resourceId": "123456789012",
                    "tagKeys": ["Environment", "Team:Name"]
                }
            }
        }

        tag_ssm_main.lambda_handler(event, None)

        mock_assume_role.assert_called_once_with(
            role_arn="arn:aws:iam::123456789012:role/test-role"
        )
        mock_delete_ssm.assert_called_once()
        call_kwargs = mock_delete_ssm.call_args[1]
        # Colons in tag keys are replaced with dots
        assert call_kwargs['tags'] == ["Environment", "Team.Name"]


class TestAccountTagToSsmParameterRoleAssumptionFails:
    """Test error: role assumption fails gracefully."""

    @patch.object(tag_ssm_main, 'assume_role_arn')
    def test_role_assumption_failure_raises_runtime_error(
        self, mock_assume_role, monkeypatch
    ):
        """When role assumption raises ClientError, RuntimeError is raised."""
        from botocore.exceptions import ClientError

        monkeypatch.setenv("ASSUMED_ROLE_NAME", "test-role")

        mock_assume_role.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Not authorized"}},
            "AssumeRole"
        )

        event = {
            "detail": {
                "eventName": "TagResource",
                "requestParameters": {
                    "resourceId": "123456789012",
                    "tags": [{"key": "Env", "value": "Dev"}]
                }
            }
        }

        with pytest.raises(RuntimeError):
            tag_ssm_main.lambda_handler(event, None)


class TestAccountTagToSsmParameterMissingFields:
    """Test error: missing required event fields."""

    def test_missing_detail_key_raises_runtime_error(self, monkeypatch):
        """When 'detail' key is missing, RuntimeError is raised."""
        monkeypatch.setenv("ASSUMED_ROLE_NAME", "test-role")

        event = {"source": "aws.organizations"}

        with pytest.raises(RuntimeError):
            tag_ssm_main.lambda_handler(event, None)

    def test_missing_resource_id_raises_runtime_error(self, monkeypatch):
        """When 'resourceId' key is missing, RuntimeError is raised."""
        monkeypatch.setenv("ASSUMED_ROLE_NAME", "test-role")

        event = {
            "detail": {
                "eventName": "TagResource",
                "requestParameters": {
                    "tags": [{"key": "Env", "value": "Dev"}]
                }
            }
        }

        with pytest.raises(RuntimeError):
            tag_ssm_main.lambda_handler(event, None)


class TestAccountTagToSsmParameterUnknownEvent:
    """Test unknown event name logs warning but does not error."""

    @patch.object(tag_ssm_main, 'assume_role_arn')
    def test_unknown_event_name_no_error(
        self, mock_assume_role, monkeypatch
    ):
        """Unknown eventName logs warning, does not call create/delete."""
        monkeypatch.setenv("ASSUMED_ROLE_NAME", "test-role")

        mock_assume_role.return_value = {
            "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "aws_session_token": "FwoGZXIvYXdzEA..."
        }

        event = {
            "detail": {
                "eventName": "SomeOtherEvent",
                "requestParameters": {
                    "resourceId": "123456789012"
                }
            }
        }

        # Should not raise
        tag_ssm_main.lambda_handler(event, None)
