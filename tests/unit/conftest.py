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
    organizations_client.create_organizational_unit(
        ParentId=organizations_client.list_roots()["Roots"][0]["Id"],
        Name="ou-test-1",
    )
    ou_parent_id = (
        organizations_client.list_children(
            ParentId=organizations_client.list_roots()["Roots"][0]["Id"],
            ChildType="ORGANIZATIONAL_UNIT",
        )
    )["Children"][0]["Id"]
    organizations_client.create_organizational_unit(
        ParentId=ou_parent_id, Name="ou-test-2"
    )
    organizations_client.create_organizational_unit(
        ParentId=ou_parent_id, Name="ou-test-3"
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
def stubbed_servicecatalog_client_describe_product(aws_credentials, request):
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


PRODUCT_CREATE_UPDATE_RESPONSE = {
    "RecordDetail": {
        "RecordId": "testId1",
        "ProvisionedProductName": "testProvisionedProduct",
        "Status": "CREATED",
        "CreatedTime": datetime(2015, 1, 1),
        "UpdatedTime": datetime(2015, 1, 1),
        "ProvisionedProductType": "Test",
        "RecordType": "Test",
        "ProvisionedProductId": "testProduct",
        "ProductId": "testProductId1",
        "ProvisioningArtifactId": "artifactId1",
        "PathId": "string",
        "RecordTags": [
            {"Key": "tag1", "Value": "value1"},
            {"Key": "param1", "Value": "value1"},
        ],
        "LaunchRoleArn": "aRoleArn",
    }
}
PRODUCT_CREATE_UPDATE_EXPECTED_PARAMS = {
    "ProductName": "testProduct",
    "ProvisionedProductName": "testProvisionedProduct",
    "ProvisioningArtifactId": "testId1",
    "ProvisioningParameters": [{"Key": "param1", "Value": "value1"}],
    "Tags": [
        {"Key": "tag1", "Value": "value1"},
        {"Key": "SCParameter:param1", "Value": "value1"},
    ],
}


@pytest.fixture
def stubbed_servicecatalog_client_provision_product(aws_credentials):
    """Stubbed service catalog provision new product call

    Args:
        aws_credentials (_type_): Mocked creds to prevent unintended side effects
    """
    servicecatalog_client = botocore.session.get_session().create_client(
        "servicecatalog", region_name="us-east-1"
    )
    stubber = Stubber(servicecatalog_client)

    provision_product_response = PRODUCT_CREATE_UPDATE_RESPONSE
    provision_product_expected_params = PRODUCT_CREATE_UPDATE_EXPECTED_PARAMS

    stubber.add_response(
        "provision_product",
        provision_product_response,
        provision_product_expected_params,
    )
    stubber.activate()
    return servicecatalog_client


@pytest.fixture
def stubbed_servicecatalog_client_update_provisioned_product(aws_credentials):
    """Stubbed service catalog update new product call

    Args:
        aws_credentials (_type_): Mocked creds to prevent unintended side effects
    """
    servicecatalog_client = botocore.session.get_session().create_client(
        "servicecatalog", region_name="us-east-1"
    )
    stubber = Stubber(servicecatalog_client)

    update_provisioned_product_response = PRODUCT_CREATE_UPDATE_RESPONSE
    update_provisioned_product_expected_params = PRODUCT_CREATE_UPDATE_EXPECTED_PARAMS

    stubber.add_response(
        "update_provisioned_product",
        update_provisioned_product_response,
        update_provisioned_product_expected_params,
    )
    stubber.activate()
    return servicecatalog_client
