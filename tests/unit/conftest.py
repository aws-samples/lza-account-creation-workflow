# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
from datetime import datetime
import boto3
import botocore
from botocore.stub import Stubber
import pytest
from moto import mock_organizations, mock_ses, mock_codepipeline, mock_iam
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


@pytest.fixture
def mock_codepipeline_role(aws_credentials):
    """Mocked role for codepipeline to use when testing objects"""
    with mock_iam():
        iam = boto3.client("iam", region_name="us-east-1")
        iam.create_role(
            RoleName="test-role",
            AssumeRolePolicyDocument='{"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "codepipeline.amazonaws.com"}, "Action": "sts:AssumeRole"}]}',
        )
        yield iam.get_role(RoleName="test-role")
        iam.delete_role(RoleName="test-role")


@pytest.fixture(scope="function")
def organizations_client(aws_credentials):
    """Mocked boto3 org client to use when testing objects"""
    with mock_organizations():
        yield boto3.client("organizations", region_name="us-east-1")


@pytest.fixture(scope="function")
def mocked_codepipeline_client(aws_credentials, mock_codepipeline_role):
    """Mocked boto3 codepipeline client to use when testing objects"""
    with mock_codepipeline():
        cp_client = boto3.client("codepipeline", region_name="us-east-1")
        cp_client.create_pipeline(
            pipeline={
                "name": "test-pipeline",
                "roleArn": mock_codepipeline_role["Role"]["Arn"],
                "stages": [
                    {"name": "Source", "actions": []},
                    {"name": "Build", "actions": []},
                ],
            }
        )
        yield cp_client


@pytest.fixture(scope="function")
def mocked_codebuild_client(aws_credentials):
    """Mocked boto3 codebuild client to use when testing objects"""
    with mock_codepipeline():
        cb_client = boto3.client("codebuild", region_name="us-east-1")
        yield cb_client


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


@pytest.fixture
def stubbed_get_codepipeline_execution(aws_credentials):
    """Stubbed service catalog update new product call

    Args:
        aws_credentials (_type_): Mocked creds to prevent unintended side effects
    """
    codepipeline_client = botocore.session.get_session().create_client(
        "codepipeline", region_name="us-east-1"
    )
    stubber = Stubber(codepipeline_client)

    get_codepipeline_execution_response = {
        "pipelineExecution": {
            "pipelineName": "testPipeline",
            "pipelineVersion": 1,
            "status": "Succeeded",
            "artifactRevisions": [
                {
                    "name": "testArtifact",
                    "revisionId": "testRevisionId",
                    "revisionChangeIdentifier": "testRevisionChangeIdentifier",
                    "revisionSummary": "testRevisionSummary",
                    "created": datetime(2015, 1, 1),
                    "revisionUrl": "testRevisionUrl",
                }
            ],
        }
    }

    get_codepipeline_execution_expected_params = {
        "pipelineName": "testPipeline",
        "pipelineExecutionId": "testPipelineExecutionId",
    }
    stubber.add_response(
        "get_pipeline_execution",
        get_codepipeline_execution_response,
        get_codepipeline_execution_expected_params,
    )
    stubber.activate()
    return codepipeline_client


@pytest.fixture
def stubbed_list_codepipeline_running_executions(aws_credentials):
    """Stubbed service catalog update new product call

    Args:
        aws_credentials (_type_): Mocked creds to prevent unintended side effects
    """
    codepipeline_client = botocore.session.get_session().create_client(
        "codepipeline", region_name="us-east-1"
    )
    stubber = Stubber(codepipeline_client)

    list_codepipeline_executions_response = {
        "pipelineExecutionSummaries": [
            {
                "pipelineExecutionId": "testPipelineExecution123",
                "status": "InProgress",
                "startTime": datetime(2015, 1, 1),
                "lastUpdateTime": datetime(2015, 1, 1),
                "sourceRevisions": [
                    {
                        "actionName": "string",
                        "revisionId": "string",
                        "revisionSummary": "string",
                        "revisionUrl": "string",
                    },
                ],
                "trigger": {
                    "triggerType": "StartPipelineExecution",
                    "triggerDetail": "string",
                },
                "stopTrigger": {"reason": "string"},
            },
            {
                "pipelineExecutionId": "testPipelineExecution987",
                "status": "Complete",
                "startTime": datetime(2015, 1, 1),
                "lastUpdateTime": datetime(2015, 1, 1),
                "sourceRevisions": [
                    {
                        "actionName": "string",
                        "revisionId": "string",
                        "revisionSummary": "string",
                        "revisionUrl": "string",
                    },
                ],
                "trigger": {
                    "triggerType": "StartPipelineExecution",
                    "triggerDetail": "string",
                },
                "stopTrigger": {"reason": "string"},
            },
        ]
    }
    list_codepipeline_executions_expected_params = {
        "pipelineName": "testPipeline",
    }
    stubber.add_response(
        "list_pipeline_executions",
        list_codepipeline_executions_response,
        list_codepipeline_executions_expected_params,
    )
    stubber.activate()
    return codepipeline_client


@pytest.fixture
def stubbed_start_pipeline_execution(aws_credentials):
    """Stubbed service catalog update new product call

    Args:
        aws_credentials (_type_): Mocked creds to prevent unintended side effects
    """
    codepipeline_client = botocore.session.get_session().create_client(
        "codepipeline", region_name="us-east-1"
    )
    stubber = Stubber(codepipeline_client)

    start_pipeline_executions_response = {
        "pipelineExecutionId": "testPipelineExecution123"
    }
    start_pipeline_executions_expected_params = {
        "name": "testPipeline",
    }
    stubber.add_response(
        "start_pipeline_execution",
        start_pipeline_executions_response,
        start_pipeline_executions_expected_params,
    )
    stubber.activate()
    return codepipeline_client


@pytest.fixture
def stubbed_list_builds_and_batch_get(aws_credentials):
    """Stubbed service catalog update new product call

    Args:
        aws_credentials (_type_): Mocked creds to prevent unintended side effects
    """
    codebuild_client = botocore.session.get_session().create_client(
        "codebuild", region_name="us-east-1"
    )
    stubber = Stubber(codebuild_client)

    list_builds_response = {
        "ids": ["testBuildId1", "testBuildId2"],
    }
    list_builds_expected_params = {
        "projectName": "lzac-account-decommission",
    }
    batch_get_builds_response = {
        "builds": [
            {
                "id": "testBuildId1",
                "arn": "string",
                "buildNumber": 123,
                "startTime": datetime(2015, 1, 1),
                "endTime": datetime(2015, 1, 1),
                "currentPhase": "string",
                "buildStatus": "SUCCEEDED",
                "sourceVersion": "string",
                "resolvedSourceVersion": "string",
                "projectName": "string",
            },
            {
                "id": "testBuildId2",
                "arn": "string",
                "buildNumber": 123,
                "startTime": datetime(2015, 1, 1),
                "endTime": datetime(2015, 1, 1),
                "currentPhase": "string",
                "buildStatus": "IN_PROGRESS",
                "sourceVersion": "string",
                "resolvedSourceVersion": "string",
                "projectName": "string",
            },
        ]
    }
    batch_get_builds_expected_params = {
        "ids": ["testBuildId1", "testBuildId2"],
    }

    stubber.add_response(
        "list_builds_for_project",
        list_builds_response,
        list_builds_expected_params,
    )
    stubber.add_response(
        "batch_get_builds",
        batch_get_builds_response,
        batch_get_builds_expected_params,
    )
    stubber.activate()
    return codebuild_client
