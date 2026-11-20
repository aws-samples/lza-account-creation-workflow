# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import sys
import json
import importlib.util
from unittest.mock import patch, MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws
from moto.core import DEFAULT_ACCOUNT_ID

# Set region before importing module (module-level boto3 clients need it)
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

# Import with unique module name to avoid conflicts with other test files
_spec = importlib.util.spec_from_file_location(
    "name_availability_main",
    "app/lambda_src/api/NameAvailability/main.py"
)
name_availability_main = importlib.util.module_from_spec(_spec)
sys.modules["name_availability_main"] = name_availability_main
_spec.loader.exec_module(name_availability_main)

lambda_handler = name_availability_main.lambda_handler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def aws_credentials(monkeypatch):
    """Mocked AWS creds for moto tests"""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def api_event():
    """Helper to build API Gateway event with query parameters"""
    def _make_event(account_name=None):
        event = {}
        if account_name is not None:
            event["queryStringParameters"] = {"account_name": account_name}
        else:
            event["queryStringParameters"] = None
        return event
    return _make_event


# ---------------------------------------------------------------------------
# Tests: Missing or Invalid Parameters
# ---------------------------------------------------------------------------


class TestNameAvailabilityValidation:
    """Tests for input validation"""

    def test_missing_query_params_returns_400(self, aws_credentials, api_event):
        """Missing queryStringParameters returns 400"""
        event = {"queryStringParameters": None}
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"]["code"] == "MISSING_PARAMETER"
        assert "account_name" in body["error"]["message"]

    def test_empty_query_params_returns_400(self, aws_credentials, api_event):
        """Empty queryStringParameters dict returns 400"""
        event = {"queryStringParameters": {}}
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"]["code"] == "MISSING_PARAMETER"

    def test_missing_account_name_param_returns_400(
        self, aws_credentials, api_event
    ):
        """Query params without account_name returns 400"""
        event = {"queryStringParameters": {"other_param": "value"}}
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"]["code"] == "MISSING_PARAMETER"

    def test_invalid_account_name_too_short_returns_400(
        self, aws_credentials, api_event
    ):
        """Account name too short (< 3 chars) returns 400"""
        event = api_event("ab")
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_invalid_account_name_special_chars_returns_400(
        self, aws_credentials, api_event
    ):
        """Account name with special characters returns 400"""
        event = api_event("test@account!")
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_invalid_account_name_starts_with_hyphen_returns_400(
        self, aws_credentials, api_event
    ):
        """Account name starting with hyphen returns 400"""
        event = api_event("-invalid-name")
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400

    def test_invalid_account_name_ends_with_hyphen_returns_400(
        self, aws_credentials, api_event
    ):
        """Account name ending with hyphen returns 400"""
        event = api_event("invalid-name-")
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400

    def test_invalid_account_name_spaces_returns_400(
        self, aws_credentials, api_event
    ):
        """Account name with spaces returns 400"""
        event = api_event("has spaces")
        response = lambda_handler(event, None)
        assert response["statusCode"] == 400


# ---------------------------------------------------------------------------
# Tests: Account Exists
# ---------------------------------------------------------------------------


class TestNameAvailabilityAccountExists:
    """Tests for when account name already exists"""

    @patch("name_availability_main.ORG_CLIENT")
    def test_account_exists_returns_200_with_id(
        self, mock_org, aws_credentials, api_event
    ):
        """Existing account name returns 200 with the account ID"""
        # Mock paginator that returns matching account
        mock_paginator = MagicMock()
        mock_org.get_paginator.return_value = mock_paginator
        mock_pages = MagicMock()
        mock_paginator.paginate.return_value = mock_pages
        mock_pages.search.return_value = iter(["111122223333"])

        event = api_event("existing-account")
        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body == "111122223333"

    @patch("name_availability_main.ORG_CLIENT")
    def test_account_available_returns_200_with_null(
        self, mock_org, aws_credentials, api_event
    ):
        """Available account name returns 200 with null body"""
        mock_paginator = MagicMock()
        mock_org.get_paginator.return_value = mock_paginator
        mock_pages = MagicMock()
        mock_paginator.paginate.return_value = mock_pages
        mock_pages.search.return_value = iter([""])

        event = api_event("available-account")
        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body is None


# ---------------------------------------------------------------------------
# Tests: Account Available (using moto)
# ---------------------------------------------------------------------------


class TestNameAvailabilityWithMoto:
    """Tests using moto mock for AWS Organizations"""

    def test_account_not_found_returns_null(self, aws_credentials):
        """Account not in Organizations returns null"""
        with mock_aws():
            org_client = boto3.client("organizations", region_name="us-east-1")
            org_client.create_organization()

            with patch("name_availability_main.ORG_CLIENT", org_client):
                event = {"queryStringParameters": {"account_name": "nonexistent-acct"}}
                response = lambda_handler(event, None)

            assert response["statusCode"] == 200
            body = json.loads(response["body"])
            assert body is None


# ---------------------------------------------------------------------------
# Tests: Error Handling
# ---------------------------------------------------------------------------


class TestNameAvailabilityErrors:
    """Tests for error handling"""

    @patch("name_availability_main.ORG_CLIENT")
    def test_aws_client_error_returns_500(
        self, mock_org, aws_credentials, api_event
    ):
        """AWS ClientError returns 500"""
        mock_org.get_paginator.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}},
            "ListAccounts"
        )

        event = api_event("test-account")
        response = lambda_handler(event, None)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["error"]["code"] == "AWS_ERROR"
        assert body["error"]["message"] == "Internal service error"

    @patch("name_availability_main.ORG_CLIENT")
    def test_unexpected_error_returns_500(
        self, mock_org, aws_credentials, api_event
    ):
        """Unexpected exception returns 500"""
        mock_org.get_paginator.side_effect = RuntimeError("unexpected")

        event = api_event("test-account")
        response = lambda_handler(event, None)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["error"]["code"] == "INTERNAL_ERROR"
