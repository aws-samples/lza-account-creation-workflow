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
os.environ.setdefault("ASSUMED_VALIDATION_ROLE_NAME", "validation-role")

# Add lambda layer to path
sys.path.insert(0, 'app/lambda_layer/account_creation_helper/python')

# The ValidateResources Lambda imports several local modules.
# We add its directory to sys.path to resolve them all.
_validate_dir = 'app/lambda_src/stepfunction/ValidateResources'
sys.path.insert(0, _validate_dir)

# Remove any cached 'helper' module from other test files to avoid collision
sys.modules.pop("helper", None)
sys.modules.pop("organizations_helper", None)
sys.modules.pop("iam_helper", None)
sys.modules.pop("ssm_helper", None)
sys.modules.pop("s3_helper", None)

_spec = importlib.util.spec_from_file_location(
    "validate_resources_main",
    "app/lambda_src/stepfunction/ValidateResources/main.py"
)
validate_main = importlib.util.module_from_spec(_spec)
sys.modules["validate_resources_main"] = validate_main
_spec.loader.exec_module(validate_main)


class TestValidateResourcesAllPass:
    """Test: validation passes all checks."""

    @patch.object(validate_main, 'ValidateS3')
    @patch.object(validate_main, 'ValidateSsm')
    @patch.object(validate_main, 'ValidateIam')
    @patch.object(validate_main, 'assume_role_arn')
    @patch.object(validate_main, 'is_account_exist_in_ou')
    @patch.object(validate_main, 'get_services_to_validate')
    def test_all_validations_pass_returns_completed(
        self, mock_get_services, mock_ou_check, mock_assume_role,
        mock_iam_cls, mock_ssm_cls, mock_s3_cls, monkeypatch
    ):
        """When all validations pass, ValidationStatus is COMPLETED."""
        monkeypatch.setenv("ASSUMED_VALIDATION_ROLE_NAME", "validation-role")

        mock_get_services.return_value = {
            "validate": {
                "organizationalUnits": {
                    "Workloads": {
                        "iam": {"roles": ["role-a"]},
                        "ssm": {"parameters": ["/test/param"]},
                        "s3": {"buckets": ["test-bucket"]},
                        "config": {"rules": []}
                    }
                }
            }
        }

        mock_ou_check.return_value = {"Status": "COMPLETED", "Service": "Organizations"}
        mock_assume_role.return_value = {
            "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "aws_session_token": "FwoGZXIvYXdzEA..."
        }

        mock_iam = MagicMock()
        mock_iam.iam_role_exist.return_value = {"Status": "COMPLETED", "Service": "IAM"}
        mock_iam_cls.return_value = mock_iam

        mock_ssm = MagicMock()
        mock_ssm.ssm_parameter_exist.return_value = {"Status": "COMPLETED", "Service": "SSM"}
        mock_ssm_cls.return_value = mock_ssm

        mock_s3 = MagicMock()
        mock_s3.s3_bucket_exist.return_value = {"Status": "COMPLETED", "Service": "S3"}
        mock_s3_cls.return_value = mock_s3

        event = {
            "Payload": {
                "AccountInfo": {
                    "AccountName": "test-account",
                    "ManagedOrganizationalUnit": "Workloads/Team-A"
                },
                "Account": {
                    "Outputs": {
                        "AccountId": "123456789012"
                    }
                }
            }
        }

        result = validate_main.lambda_handler(event, None)

        assert result['ValidationStatus'] == "COMPLETED"
        assert len(result['ValidationInformation']) > 0
        mock_assume_role.assert_called_once_with(
            role_arn="arn:aws:iam::123456789012:role/validation-role"
        )


class TestValidateResourcesInProgress:
    """Test: validation fails with in-progress status."""

    @patch.object(validate_main, 'ValidateS3')
    @patch.object(validate_main, 'ValidateSsm')
    @patch.object(validate_main, 'ValidateIam')
    @patch.object(validate_main, 'assume_role_arn')
    @patch.object(validate_main, 'is_account_exist_in_ou')
    @patch.object(validate_main, 'get_services_to_validate')
    def test_in_progress_validation_returns_in_progress(
        self, mock_get_services, mock_ou_check, mock_assume_role,
        mock_iam_cls, mock_ssm_cls, mock_s3_cls, monkeypatch
    ):
        """When any validation is InProgress, status is InProgress."""
        monkeypatch.setenv("ASSUMED_VALIDATION_ROLE_NAME", "validation-role")

        mock_get_services.return_value = {
            "validate": {
                "organizationalUnits": {
                    "Workloads": {
                        "iam": {"roles": ["role-a"]},
                        "ssm": {"parameters": []},
                        "s3": {"buckets": []},
                        "config": {"rules": []}
                    }
                }
            }
        }

        mock_ou_check.return_value = {"Status": "COMPLETED", "Service": "Organizations"}
        mock_assume_role.return_value = {
            "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "aws_session_token": "FwoGZXIvYXdzEA..."
        }

        mock_iam = MagicMock()
        mock_iam.iam_role_exist.return_value = {"Status": "InProgress", "Service": "IAM"}
        mock_iam_cls.return_value = mock_iam

        mock_ssm_cls.return_value = MagicMock()
        mock_s3_cls.return_value = MagicMock()

        event = {
            "Payload": {
                "AccountInfo": {
                    "AccountName": "test-account",
                    "ManagedOrganizationalUnit": "Workloads/Team-A"
                },
                "Account": {
                    "Outputs": {
                        "AccountId": "123456789012"
                    }
                }
            }
        }

        result = validate_main.lambda_handler(event, None)

        assert result['ValidationStatus'] == "InProgress"


class TestValidateResourcesRoleAssumptionFails:
    """Test: role assumption for cross-account validation fails."""

    @patch.object(validate_main, 'assume_role_arn')
    @patch.object(validate_main, 'is_account_exist_in_ou')
    @patch.object(validate_main, 'get_services_to_validate')
    def test_role_assumption_failure_raises_runtime_error(
        self, mock_get_services, mock_ou_check, mock_assume_role, monkeypatch
    ):
        """When assume_role_arn raises ClientError, RuntimeError is raised."""
        from botocore.exceptions import ClientError

        monkeypatch.setenv("ASSUMED_VALIDATION_ROLE_NAME", "validation-role")

        mock_get_services.return_value = {
            "validate": {
                "organizationalUnits": {
                    "Workloads": {
                        "iam": {"roles": ["role-a"]},
                        "ssm": {"parameters": []},
                        "s3": {"buckets": []},
                        "config": {"rules": []}
                    }
                }
            }
        }

        mock_ou_check.return_value = {"Status": "COMPLETED", "Service": "Organizations"}
        mock_assume_role.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Not authorized"}},
            "AssumeRole"
        )

        event = {
            "Payload": {
                "AccountInfo": {
                    "AccountName": "test-account",
                    "ManagedOrganizationalUnit": "Workloads/Team-A"
                },
                "Account": {
                    "Outputs": {
                        "AccountId": "123456789012"
                    }
                }
            }
        }

        with pytest.raises(RuntimeError):
            validate_main.lambda_handler(event, None)


class TestValidateResourcesMissingFields:
    """Test: missing required fields raises RuntimeError."""

    def test_missing_payload_raises_runtime_error(self, monkeypatch):
        """When Payload is missing, RuntimeError/TypeError is raised."""
        monkeypatch.setenv("ASSUMED_VALIDATION_ROLE_NAME", "validation-role")

        event = {"SomeOtherKey": "value"}

        with pytest.raises((RuntimeError, TypeError)):
            validate_main.lambda_handler(event, None)

    @patch.object(validate_main, 'get_services_to_validate')
    def test_missing_account_outputs_raises_runtime_error(
        self, mock_get_services, monkeypatch
    ):
        """When Account.Outputs.AccountId is missing, RuntimeError."""
        monkeypatch.setenv("ASSUMED_VALIDATION_ROLE_NAME", "validation-role")

        mock_get_services.return_value = {
            "validate": {"organizationalUnits": {}}
        }

        event = {
            "Payload": {
                "AccountInfo": {
                    "AccountName": "test-account",
                    "ManagedOrganizationalUnit": "Workloads"
                }
            }
        }

        with pytest.raises(RuntimeError):
            validate_main.lambda_handler(event, None)


class TestValidateResourcesNoMatchingOU:
    """Test: OU not in validation config produces empty validation."""

    @patch.object(validate_main, 'ValidateS3')
    @patch.object(validate_main, 'ValidateSsm')
    @patch.object(validate_main, 'ValidateIam')
    @patch.object(validate_main, 'assume_role_arn')
    @patch.object(validate_main, 'is_account_exist_in_ou')
    @patch.object(validate_main, 'get_services_to_validate')
    def test_no_matching_ou_returns_completed(
        self, mock_get_services, mock_ou_check, mock_assume_role,
        mock_iam_cls, mock_ssm_cls, mock_s3_cls, monkeypatch
    ):
        """When OU doesn't match config, only OU check runs; status COMPLETED."""
        monkeypatch.setenv("ASSUMED_VALIDATION_ROLE_NAME", "validation-role")

        mock_get_services.return_value = {
            "validate": {
                "organizationalUnits": {
                    "Sandbox": {
                        "iam": {"roles": ["role-x"]},
                        "ssm": {"parameters": []},
                        "s3": {"buckets": []},
                        "config": {"rules": []}
                    }
                }
            }
        }

        mock_ou_check.return_value = {"Status": "COMPLETED", "Service": "Organizations"}
        mock_assume_role.return_value = {
            "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "aws_session_token": "FwoGZXIvYXdzEA..."
        }
        mock_iam_cls.return_value = MagicMock()
        mock_ssm_cls.return_value = MagicMock()
        mock_s3_cls.return_value = MagicMock()

        event = {
            "Payload": {
                "AccountInfo": {
                    "AccountName": "test-account",
                    "ManagedOrganizationalUnit": "Workloads/Team-A"
                },
                "Account": {
                    "Outputs": {
                        "AccountId": "123456789012"
                    }
                }
            }
        }

        result = validate_main.lambda_handler(event, None)

        assert result['ValidationStatus'] == "COMPLETED"
        # Only the OU check result
        assert len(result['ValidationInformation']) == 1
