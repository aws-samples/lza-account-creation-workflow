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
    "create_additional_resources_helper",
    "app/lambda_src/stepfunction/CreateAdditionalResources/helper.py"
)
_helper_mod = importlib.util.module_from_spec(_helper_spec)
_helper_spec.loader.exec_module(_helper_mod)

# Inject the helper into sys.modules so the main module picks it up
_original_helper = sys.modules.get("helper")
sys.modules["helper"] = _helper_mod

_spec = importlib.util.spec_from_file_location(
    "create_additional_resources_main",
    "app/lambda_src/stepfunction/CreateAdditionalResources/main.py"
)
create_resources_main = importlib.util.module_from_spec(_spec)
sys.modules["create_additional_resources_main"] = create_resources_main
_spec.loader.exec_module(create_resources_main)

# Restore original helper module
if _original_helper is not None:
    sys.modules["helper"] = _original_helper
else:
    sys.modules.pop("helper", None)


class TestCreateAdditionalResourcesHappyPath:
    """Test happy path: creates account alias and tags resources."""

    @patch.object(create_resources_main, 'create_account_tags')
    @patch.object(create_resources_main, 'create_account_alias')
    @patch.object(create_resources_main, 'assume_role_arn')
    def test_creates_alias_and_tags(
        self, mock_assume_role, mock_create_alias, mock_create_tags, monkeypatch
    ):
        """Creates account alias and organization tags on success."""
        monkeypatch.setenv("ASSUMED_ROLE_NAME", "test-role")

        mock_assume_role.return_value = {
            "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "aws_session_token": "FwoGZXIvYXdzEA..."
        }

        event = {
            "Payload": {
                "AccountInfo": {
                    "AccountName": "My-Test-Account",
                    "ManagedOrganizationalUnit": "Workloads",
                    "SupportDL": "test@example.com",
                    "AccountTags": [
                        {"Key": "CostCenter", "Value": "12345"}
                    ]
                },
                "Account": {
                    "Outputs": {
                        "AccountId": "123456789012",
                        "ProvisionedProductId": "pp-abc123"
                    }
                }
            }
        }

        result = create_resources_main.lambda_handler(event, None)

        mock_assume_role.assert_called_once_with(
            role_arn="arn:aws:iam::123456789012:role/test-role"
        )
        mock_create_alias.assert_called_once_with(
            creds=mock_assume_role.return_value,
            alias="my-test-account"
        )
        mock_create_tags.assert_called_once()
        call_kwargs = mock_create_tags.call_args[1]
        assert call_kwargs['account_id'] == "123456789012"
        # SC tag + custom tag
        assert {"Key": "SCProvisionedProductId", "Value": "pp-abc123"} in call_kwargs['tags']
        assert {"Key": "CostCenter", "Value": "12345"} in call_kwargs['tags']
        assert result == event['Payload']

    @patch.object(create_resources_main, 'create_account_tags')
    @patch.object(create_resources_main, 'create_account_alias')
    @patch.object(create_resources_main, 'assume_role_arn')
    def test_uses_provisioned_product_name_as_fallback(
        self, mock_assume_role, mock_create_alias, mock_create_tags, monkeypatch
    ):
        """Uses ProvisionedProductName if AccountName is empty."""
        monkeypatch.setenv("ASSUMED_ROLE_NAME", "test-role")

        mock_assume_role.return_value = {
            "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "aws_session_token": "FwoGZXIvYXdzEA..."
        }

        event = {
            "Payload": {
                "AccountInfo": {
                    "AccountName": "",
                    "ManagedOrganizationalUnit": "Workloads",
                    "SupportDL": "test@example.com"
                },
                "Account": {
                    "Outputs": {
                        "AccountId": "123456789012",
                        "ProvisionedProductId": "pp-abc123",
                        "ProvisionedProductName": "fallback-name"
                    }
                }
            }
        }

        create_resources_main.lambda_handler(event, None)

        mock_create_alias.assert_called_once_with(
            creds=mock_assume_role.return_value,
            alias="fallback-name"
        )


class TestCreateAdditionalResourcesRoleAssumptionFails:
    """Test error: role assumption fails."""

    @patch.object(create_resources_main, 'assume_role_arn')
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
            "Payload": {
                "AccountInfo": {
                    "AccountName": "test-account",
                    "ManagedOrganizationalUnit": "Workloads",
                    "SupportDL": "test@example.com"
                },
                "Account": {
                    "Outputs": {
                        "AccountId": "123456789012",
                        "ProvisionedProductId": "pp-abc123"
                    }
                }
            }
        }

        with pytest.raises(RuntimeError):
            create_resources_main.lambda_handler(event, None)


class TestCreateAdditionalResourcesMissingAccountInfo:
    """Test error: missing account info in payload."""

    def test_missing_payload_key_raises_runtime_error(self, monkeypatch):
        """When 'Payload' is None/missing keys, RuntimeError is raised."""
        monkeypatch.setenv("ASSUMED_ROLE_NAME", "test-role")

        event = {"Payload": None}

        with pytest.raises((RuntimeError, TypeError)):
            create_resources_main.lambda_handler(event, None)

    def test_missing_account_outputs_raises_runtime_error(self, monkeypatch):
        """When Account.Outputs is missing, RuntimeError is raised."""
        monkeypatch.setenv("ASSUMED_ROLE_NAME", "test-role")

        event = {
            "Payload": {
                "AccountInfo": {
                    "AccountName": "test-account",
                    "ManagedOrganizationalUnit": "Workloads"
                }
            }
        }

        with pytest.raises(RuntimeError):
            create_resources_main.lambda_handler(event, None)
