# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import sys
import json
import re
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import boto3
import botocore
from botocore.stub import Stubber
from botocore.exceptions import ClientError
import pytest

# Set region before importing module (module-level boto3 clients need it)
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("STEPFUNCTION_NAME", "test-sf")

sys.path.insert(0, 'app/lambda_src/api/RunStepFunction')
from main import (
    lambda_handler,
    validate_account_name,
    validate_managed_org_unit,
    generate_sf_exec_name,
    ValidationError,
)


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
    """Set required environment variables for RunStepFunction"""
    monkeypatch.setenv("STEPFUNCTION_NAME", "test-account-creation-sf")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")


@pytest.fixture
def valid_event():
    """A valid API Gateway event with proper body"""
    return {
        "body": json.dumps({
            "account_name": "lzatestaccount",
            "support_dl": "team@example.com",
            "managed_org_unit": "Workloads/Production"
        })
    }


@pytest.fixture
def valid_params():
    """Valid parameters for direct invocation (no body wrapper)"""
    return {
        "account_name": "lzatestaccount",
        "support_dl": "team@example.com",
        "managed_org_unit": "Workloads/Production"
    }


# ---------------------------------------------------------------------------
# Tests: validate_account_name
# ---------------------------------------------------------------------------


class TestValidateAccountName:
    """Tests for validate_account_name function"""

    def test_valid_names(self):
        """Valid account names should not raise"""
        valid_names = [
            "abc",              # minimum length
            "lzatest01",
            "MyAccountName",
            "A1B2C3",
            "a" * 50,          # maximum length
        ]
        for name in valid_names:
            validate_account_name(name)  # should not raise

    def test_empty_name_raises(self):
        """Empty account name raises ValidationError"""
        with pytest.raises(ValidationError, match="account_name is required"):
            validate_account_name("")

    def test_none_name_raises(self):
        """None account name raises ValidationError"""
        with pytest.raises(ValidationError, match="account_name is required"):
            validate_account_name(None)

    def test_too_short_raises(self):
        """Account name shorter than 3 chars raises ValidationError"""
        with pytest.raises(ValidationError, match="between 3 and 50"):
            validate_account_name("ab")

    def test_single_char_raises(self):
        """Single character account name raises ValidationError"""
        with pytest.raises(ValidationError, match="between 3 and 50"):
            validate_account_name("a")

    def test_too_long_raises(self):
        """Account name longer than 50 chars raises ValidationError"""
        with pytest.raises(ValidationError, match="between 3 and 50"):
            validate_account_name("a" * 51)

    def test_starts_with_hyphen_raises(self):
        """Account name starting with hyphen is invalid"""
        with pytest.raises(ValidationError):
            validate_account_name("-invalidname")

    def test_ends_with_hyphen_raises(self):
        """Account name ending with hyphen is invalid"""
        with pytest.raises(ValidationError):
            validate_account_name("invalidname-")

    def test_special_characters_raises(self):
        """Account name with special chars raises ValidationError"""
        invalid_names = [
            "name with spaces",
            "name_underscore",
            "name.dot",
            "name@at",
            "name!bang",
        ]
        for name in invalid_names:
            with pytest.raises(ValidationError):
                validate_account_name(name)

    def test_yaml_injection_chars_raises(self):
        """YAML special characters are rejected (including hyphens)"""
        yaml_chars = [
            "name{brace",
            "name}brace",
            "abc[bracket",
            "abc]bracket",
            "abc:colon",
            "abc&amp",
            "abc*star",
            "abc#hash",
            "abc?question",
            "abc|pipe",
            "abc<less",
            "abc>greater",
            "abc=equal",
            "abc!excl",
            "abc%pct",
            "abc@at",
        ]
        for name in yaml_chars:
            with pytest.raises(ValidationError):
                validate_account_name(name)

    def test_hyphen_rejected_as_yaml_special(self):
        """Hyphens are rejected by YAML special char validation"""
        with pytest.raises(ValidationError, match="invalid special characters"):
            validate_account_name("lza-test-01")


# ---------------------------------------------------------------------------
# Tests: validate_managed_org_unit
# ---------------------------------------------------------------------------


class TestValidateManagedOrgUnit:
    """Tests for validate_managed_org_unit function"""

    def test_valid_ou_paths(self):
        """Valid OU paths should not raise"""
        valid_paths = [
            "Workloads",
            "Workloads/Production",
            "Workloads/Dev-Test",
            "Root/Tier1/Tier2",
            "ab",  # minimum with pattern (2 chars: start + end)
        ]
        for path in valid_paths:
            validate_managed_org_unit(path)  # should not raise

    def test_empty_raises(self):
        """Empty managed_org_unit raises ValidationError"""
        with pytest.raises(ValidationError, match="managed_org_unit is required"):
            validate_managed_org_unit("")

    def test_none_raises(self):
        """None managed_org_unit raises ValidationError"""
        with pytest.raises(ValidationError, match="managed_org_unit is required"):
            validate_managed_org_unit(None)

    def test_too_long_raises(self):
        """OU path longer than 128 chars raises ValidationError"""
        with pytest.raises(ValidationError, match="128 characters"):
            validate_managed_org_unit("a" * 129)

    def test_invalid_characters_raises(self):
        """OU path with invalid chars raises ValidationError"""
        invalid_paths = [
            "Workloads/Prod Space",
            "Workloads/Prod@Unit",
            "Workloads/Prod!Unit",
            "Workloads/Prod#Unit",
        ]
        for path in invalid_paths:
            with pytest.raises(ValidationError):
                validate_managed_org_unit(path)

    def test_starts_with_slash_raises(self):
        """OU path starting with slash is invalid"""
        with pytest.raises(ValidationError, match="alphanumeric"):
            validate_managed_org_unit("/Workloads/Production")

    def test_ends_with_slash_raises(self):
        """OU path ending with slash is invalid"""
        with pytest.raises(ValidationError, match="alphanumeric"):
            validate_managed_org_unit("Workloads/Production/")


# ---------------------------------------------------------------------------
# Tests: generate_sf_exec_name
# ---------------------------------------------------------------------------


class TestGenerateSfExecName:
    """Tests for generate_sf_exec_name function"""

    def test_contains_account_name(self):
        """Execution name contains the account name"""
        name = generate_sf_exec_name("lzatest01")
        assert name.startswith("lzatest01-")

    def test_contains_timestamp(self):
        """Execution name includes a timestamp portion"""
        name = generate_sf_exec_name("myaccount")
        # After the account name and separator, expect YYYYMMDDHHmmss
        timestamp_part = name.split("myaccount-")[1]
        assert len(timestamp_part) == 14
        assert timestamp_part.isdigit()

    def test_unique_across_calls(self):
        """Successive calls produce unique names (unless within same second)"""
        import time
        name1 = generate_sf_exec_name("test")
        time.sleep(1.1)
        name2 = generate_sf_exec_name("test")
        assert name1 != name2


# ---------------------------------------------------------------------------
# Tests: lambda_handler - Input Validation
# ---------------------------------------------------------------------------


class TestLambdaHandlerValidation:
    """Tests for lambda_handler input validation"""

    def test_invalid_json_body_returns_400(self, aws_credentials, env_vars):
        """Invalid JSON in body returns 400"""
        event = {"body": "not-valid-json{{{"}
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"]["code"] == "INVALID_JSON"

    def test_missing_account_name_returns_400(self, aws_credentials, env_vars):
        """Missing account_name returns 400"""
        event = {
            "body": json.dumps({
                "support_dl": "team@example.com",
                "managed_org_unit": "Workloads/Prod"
            })
        }
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert "account_name" in body["error"]["message"]

    def test_missing_support_dl_returns_400(self, aws_credentials, env_vars):
        """Missing support_dl returns 400"""
        event = {
            "body": json.dumps({
                "account_name": "lzatest01",
                "managed_org_unit": "Workloads/Prod"
            })
        }
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "support_dl" in body["error"]["message"]

    def test_missing_managed_org_unit_returns_400(self, aws_credentials, env_vars):
        """Missing managed_org_unit returns 400"""
        event = {
            "body": json.dumps({
                "account_name": "lzatest01",
                "support_dl": "team@example.com"
            })
        }
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "managed_org_unit" in body["error"]["message"]

    def test_account_name_too_short_returns_400(self, aws_credentials, env_vars):
        """Account name shorter than 3 chars returns 400"""
        event = {
            "body": json.dumps({
                "account_name": "ab",
                "support_dl": "team@example.com",
                "managed_org_unit": "Workloads/Prod"
            })
        }
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "between 3 and 50" in body["error"]["message"]

    def test_account_name_too_long_returns_400(self, aws_credentials, env_vars):
        """Account name longer than 50 chars returns 400"""
        event = {
            "body": json.dumps({
                "account_name": "a" * 51,
                "support_dl": "team@example.com",
                "managed_org_unit": "Workloads/Prod"
            })
        }
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "between 3 and 50" in body["error"]["message"]

    def test_account_name_special_chars_returns_400(self, aws_credentials, env_vars):
        """Account name with special characters returns 400"""
        event = {
            "body": json.dumps({
                "account_name": "test@account!",
                "support_dl": "team@example.com",
                "managed_org_unit": "Workloads/Prod"
            })
        }
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400

    def test_account_name_yaml_injection_returns_400(self, aws_credentials, env_vars):
        """Account name with YAML injection characters returns 400"""
        event = {
            "body": json.dumps({
                "account_name": "test{injection}",
                "support_dl": "team@example.com",
                "managed_org_unit": "Workloads/Prod"
            })
        }
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400

    def test_managed_org_unit_too_long_returns_400(self, aws_credentials, env_vars):
        """OU path longer than 128 chars returns 400"""
        event = {
            "body": json.dumps({
                "account_name": "lzatest01",
                "support_dl": "team@example.com",
                "managed_org_unit": "A" * 129
            })
        }
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "128 characters" in body["error"]["message"]

    def test_managed_org_unit_invalid_chars_returns_400(
        self, aws_credentials, env_vars
    ):
        """OU path with invalid characters returns 400"""
        event = {
            "body": json.dumps({
                "account_name": "lzatest01",
                "support_dl": "team@example.com",
                "managed_org_unit": "Workloads/Bad Unit!"
            })
        }
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400


# ---------------------------------------------------------------------------
# Tests: lambda_handler - Happy Path
# ---------------------------------------------------------------------------


class TestLambdaHandlerHappyPath:
    """Tests for successful execution flow"""

    @patch("main.SF_CLIENT")
    @patch("main.STS_CLIENT")
    def test_valid_request_returns_200(
        self, mock_sts, mock_sf, aws_credentials, env_vars
    ):
        """Valid request returns 200 with execution ARN"""
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}
        mock_sf.start_execution.return_value = {
            "executionArn": "arn:aws:states:us-east-1:123456789012:execution:test-sf:lzatest01-20240101120000"
        }
        mock_sf.exceptions = MagicMock()
        mock_sf.exceptions.ExecutionAlreadyExists = type(
            "ExecutionAlreadyExists", (Exception,), {}
        )

        event = {
            "body": json.dumps({
                "account_name": "lzatest01",
                "support_dl": "team@example.com",
                "managed_org_unit": "Workloads/Production"
            })
        }

        response = lambda_handler(event, None)
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "StepFunctionExecutionArn" in body
        assert body["StepFunctionExecutionArn"].startswith("arn:aws:states:")

    @patch("main.SF_CLIENT")
    @patch("main.STS_CLIENT")
    def test_direct_invocation_without_body(
        self, mock_sts, mock_sf, aws_credentials, env_vars
    ):
        """Direct invocation (no body key) uses event as params"""
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}
        mock_sf.start_execution.return_value = {
            "executionArn": "arn:aws:states:us-east-1:123456789012:execution:test-sf:lzatest01-20240101120000"
        }
        mock_sf.exceptions = MagicMock()
        mock_sf.exceptions.ExecutionAlreadyExists = type(
            "ExecutionAlreadyExists", (Exception,), {}
        )

        event = {
            "account_name": "lzatest01",
            "support_dl": "team@example.com",
            "managed_org_unit": "Workloads/Production"
        }

        response = lambda_handler(event, None)
        assert response["statusCode"] == 200

    @patch("main.SF_CLIENT")
    @patch("main.STS_CLIENT")
    def test_optional_fields_included_in_input(
        self, mock_sts, mock_sf, aws_credentials, env_vars
    ):
        """Optional fields (ad_integration, tags) are passed to SF input"""
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}
        mock_sf.start_execution.return_value = {
            "executionArn": "arn:aws:states:us-east-1:123456789012:execution:test-sf:exec-name"
        }
        mock_sf.exceptions = MagicMock()
        mock_sf.exceptions.ExecutionAlreadyExists = type(
            "ExecutionAlreadyExists", (Exception,), {}
        )

        event = {
            "body": json.dumps({
                "account_name": "lzatest01",
                "support_dl": "team@example.com",
                "managed_org_unit": "Workloads/Production",
                "ad_integration": [{"PermissionSetName": "Admin", "ActiveDirectoryGroupName": "admins"}],
                "account_tags": [{"Key": "Env", "Value": "Dev"}],
                "force_update": "true",
                "bypass_creation": "true"
            })
        }

        response = lambda_handler(event, None)
        assert response["statusCode"] == 200

        # Verify SF input included AD integration
        call_kwargs = mock_sf.start_execution.call_args[1]
        sf_input = json.loads(call_kwargs["input"])
        assert "ADIntegration" in sf_input["AccountInfo"]
        assert sf_input["AccountInfo"]["ForceUpdate"] == "true"
        assert sf_input["AccountInfo"]["BypassCreation"] == "true"


# ---------------------------------------------------------------------------
# Tests: lambda_handler - Error Handling
# ---------------------------------------------------------------------------


class TestLambdaHandlerErrors:
    """Tests for error handling in lambda_handler"""

    @patch("main.SF_CLIENT")
    @patch("main.STS_CLIENT")
    def test_aws_client_error_returns_500(
        self, mock_sts, mock_sf, aws_credentials, env_vars
    ):
        """AWS ClientError returns 500 (not 404)"""
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}
        mock_sf.start_execution.side_effect = ClientError(
            {"Error": {"Code": "StateMachineDoesNotExist", "Message": "Not found"}},
            "StartExecution"
        )
        mock_sf.exceptions = MagicMock()
        mock_sf.exceptions.ExecutionAlreadyExists = type(
            "ExecutionAlreadyExists", (Exception,), {}
        )

        event = {
            "body": json.dumps({
                "account_name": "lzatest01",
                "support_dl": "team@example.com",
                "managed_org_unit": "Workloads/Production"
            })
        }

        response = lambda_handler(event, None)
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["error"]["code"] == "AWS_ERROR"

    @patch("main.SF_CLIENT")
    @patch("main.STS_CLIENT")
    def test_unexpected_error_returns_500(
        self, mock_sts, mock_sf, aws_credentials, env_vars
    ):
        """Unexpected exception returns 500"""
        mock_sts.get_caller_identity.side_effect = RuntimeError("boom")
        mock_sf.exceptions = MagicMock()
        mock_sf.exceptions.ExecutionAlreadyExists = type(
            "ExecutionAlreadyExists", (Exception,), {}
        )

        event = {
            "body": json.dumps({
                "account_name": "lzatest01",
                "support_dl": "team@example.com",
                "managed_org_unit": "Workloads/Production"
            })
        }

        response = lambda_handler(event, None)
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["error"]["code"] == "INTERNAL_ERROR"


# ---------------------------------------------------------------------------
# Tests: Execution Name Collision Retry
# ---------------------------------------------------------------------------


class TestExecutionNameCollisionRetry:
    """Tests for execution name collision retry logic"""

    @patch("main.SF_CLIENT")
    @patch("main.STS_CLIENT")
    def test_collision_retry_succeeds_on_second_attempt(
        self, mock_sts, mock_sf, aws_credentials, env_vars
    ):
        """Execution name collision retries and succeeds"""
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}

        # First call raises collision, second succeeds
        collision_exc = type("ExecutionAlreadyExists", (Exception,), {})
        mock_sf.exceptions.ExecutionAlreadyExists = collision_exc
        mock_sf.start_execution.side_effect = [
            collision_exc("already exists"),
            {
                "executionArn": "arn:aws:states:us-east-1:123456789012:execution:test-sf:lzatest01-retry"
            }
        ]

        event = {
            "body": json.dumps({
                "account_name": "lzatest01",
                "support_dl": "team@example.com",
                "managed_org_unit": "Workloads/Production"
            })
        }

        response = lambda_handler(event, None)
        assert response["statusCode"] == 200
        assert mock_sf.start_execution.call_count == 2

    @patch("main.SF_CLIENT")
    @patch("main.STS_CLIENT")
    def test_collision_exhausts_retries_returns_500(
        self, mock_sts, mock_sf, aws_credentials, env_vars
    ):
        """All retry attempts exhausted returns 500"""
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}

        collision_exc = type("ExecutionAlreadyExists", (Exception,), {})
        mock_sf.exceptions.ExecutionAlreadyExists = collision_exc
        mock_sf.start_execution.side_effect = collision_exc("collision")

        event = {
            "body": json.dumps({
                "account_name": "lzatest01",
                "support_dl": "team@example.com",
                "managed_org_unit": "Workloads/Production"
            })
        }

        response = lambda_handler(event, None)
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["error"]["code"] == "EXECUTION_CONFLICT"
        assert mock_sf.start_execution.call_count == 3
