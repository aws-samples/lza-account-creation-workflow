# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
from datetime import datetime
import boto3
import botocore
from botocore.stub import Stubber
import pytest
from moto import mock_organizations, mock_ses
from moto.core import DEFAULT_ACCOUNT_ID
from moto.ses import ses_backends


@pytest.fixture(scope="function")
def aws_credentials(monkeypatch):
    """Mocked AWS creds for moto tests"""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture(scope="function")
def organizations_client(aws_credentials):
    """Mocked boto3 org client to use when testing objects"""
    with mock_organizations():
        yield boto3.client("organizations", region_name="us-east-1")


@pytest.fixture(scope="function")
def mocked_organization(organizations_client):
    """Mocked organization with a tag added to default account"""
    organizations_client.create_organization()
    organizations_client.tag_resource(
        ResourceId=DEFAULT_ACCOUNT_ID, Tags=[{"Key": "Owner", "Value": "Tester McTest"}]
    )


@pytest.fixture(scope="function")
def mocked_ses_backend(aws_credentials, monkeypatch):
    with mock_ses():
        ses_backend = ses_backends[DEFAULT_ACCOUNT_ID]["us-east-1"]
        monkeypatch.setenv("FROM_EMAIL_ADDRESS", "test_from@test.com")
        ses_backend.verify_email_identity("test_from@test.com")
        ses_backend.verify_email_address(address="test_from@test.com")
        monkeypatch.setenv(
            "SES_IDENTITY_ARN",
            f"arn:aws:ses:us-east-1:{DEFAULT_ACCOUNT_ID}:identity/test_from@test.com",
        )
        yield ses_backend


@pytest.fixture
def stubbed_servicecatalog_client(aws_credentials, request):
    servicecatalog_client = botocore.session.get_session().create_client(
        "servicecatalog", region_name="us-east-1"
    )
    stubber = Stubber(servicecatalog_client)
    if request.param != "testProduct":
        describe_product_response = {}
    else:
        describe_product_response = {
            "ProductViewSummary": {
                "ProductId": "testId",
                "Name": "testProduct",
                "Owner": "testOwner",
                "ShortDescription": "testDescription",
                "Type": "CLOUD_FORMATION_TEMPLATE",
                "Distributor": "testDistributor",
                "HasDefaultPath": True,
                "SupportEmail": "testEmail",
                "SupportDescription": "testDescription",
                "SupportUrl": "testUrl",
            },
            "ProvisioningArtifacts": [
                {
                    "Id": "testId1",
                    "Name": "testProduct1",
                    "Description": "testDescription1",
                    "CreatedTime": datetime(2022, 1, 1),
                    "Guidance": "DEFAULT",
                },
                {
                    "Id": "testId2",
                    "Name": "testProduct2",
                    "Description": "testDescription2",
                    "CreatedTime": datetime(2022, 1, 1),
                    "Guidance": "DEPRECATED",
                },
            ],
            "Budgets": [
                {"BudgetName": "string"},
            ],
            "LaunchPaths": [
                {"Id": "string", "Name": "string"},
            ],
        }

    describe_product_expected_params = {
        "Name": request.param,
    }

    stubber.add_response(
        "describe_product", describe_product_response, describe_product_expected_params
    )
    stubber.activate()
    return servicecatalog_client
