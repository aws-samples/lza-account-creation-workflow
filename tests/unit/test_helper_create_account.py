# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from app.lambda_src.stepfunction.CreateAccount import helper
import pytest
from unittest.mock import patch
import boto3
import yaml


def test_build_root_email_address(monkeypatch):
    """Test build root email address method"""
    monkeypatch.setenv("ROOT_EMAIL_PREFIX", "pytest")
    monkeypatch.setenv("ROOT_EMAIL_DOMAIN", "example.com")
    test_root_email = helper.build_root_email_address("test-account1")
    assert test_root_email == "pytest+test-account1@example.com"


def test_build_root_email_with_extra_chars(monkeypatch):
    """Test build root email address method"""
    monkeypatch.setenv("ROOT_EMAIL_PREFIX", "pytest")
    monkeypatch.setenv("ROOT_EMAIL_DOMAIN", "@example.com")
    test_root_email = helper.build_root_email_address("test account 1")
    assert test_root_email == "pytest+test-account-1@example.com"


def test_raises_exception(monkeypatch):
    """Test build root email address method"""
    monkeypatch.delenv("ROOT_EMAIL_PREFIX", raising=False)
    monkeypatch.delenv("ROOT_EMAIL_DOMAIN", raising=False)
    with pytest.raises(helper.MissingEnvironmentVariableException) as missing_exception:
        helper.build_root_email_address("blah")
        print(missing_exception)


@pytest.mark.parametrize(
    "stubbed_servicecatalog_client_describe_product", ["testProduct"], indirect=True
)
def test_get_provisioning_artifact_id(stubbed_servicecatalog_client_describe_product):
    """Test the get_provisioning_artifact_id funciton using botocore Stubber"""
    test_product_id = helper.get_provisioning_artifact_id(
        "testProduct", stubbed_servicecatalog_client_describe_product
    )
    assert test_product_id == "testId1"


@pytest.mark.parametrize(
    "stubbed_servicecatalog_client_describe_product", ["fakeProduct"], indirect=True
)
def test_get_provisioning_artifact_id_no_product(
    stubbed_servicecatalog_client_describe_product,
):
    """Test the get_provisioning_artifact_id funciton using botocore Stubber"""
    with pytest.raises(KeyError):
        helper.get_provisioning_artifact_id(
            "fakeProduct", stubbed_servicecatalog_client_describe_product
        )


def test_check_delay():
    """Test check delay method"""
    test_delay = helper.check_delay()
    assert test_delay == 5


def test_build_service_catalog_parameters():
    """Test build service catalog parameters method"""
    test_parameters = helper.build_service_catalog_parameters(
        {"accountId": "test_account_id", "email": "test@example.com"}
    )
    assert test_parameters == [
        {"Key": "accountId", "Value": "test_account_id"},
        {"Key": "email", "Value": "test@example.com"},
    ]


def test_create_update_provision_product_create(
    stubbed_servicecatalog_client_provision_product,
):
    """Test create_update_provision_product method"""
    test_provision_product = helper.create_update_provision_product(
        product_name="testProduct",
        pa_id="testId1",
        pp_name="testProvisionedProduct",
        client=stubbed_servicecatalog_client_provision_product,
        params=[{"Key": "param1", "Value": "value1"}],
        tags=[{"Key": "tag1", "Value": "value1"}],
        update="False",
    )
    assert (
        test_provision_product["RecordDetail"]["ProvisionedProductName"]
        == "testProvisionedProduct"
    )


def test_create_update_provision_product_update(
    stubbed_servicecatalog_client_update_provisioned_product,
):
    """Test create_update_provision_product method"""
    test_provision_product = helper.create_update_provision_product(
        product_name="testProduct",
        pa_id="testId1",
        pp_name="testProvisionedProduct",
        client=stubbed_servicecatalog_client_update_provisioned_product,
        params=[{"Key": "param1", "Value": "value1"}],
        tags=[{"Key": "tag1", "Value": "value1"}],
        update="true",
    )
    assert (
        test_provision_product["RecordDetail"]["ProvisionedProductName"]
        == "testProvisionedProduct"
    )


def test_list_children_ous(organizations_client, mocked_organization):
    """Test list_children_ous method"""
    parent_id = (
        organizations_client.list_children(
            ParentId=organizations_client.list_roots()["Roots"][0]["Id"],
            ChildType="ORGANIZATIONAL_UNIT",
        )
    )["Children"][0]["Id"]
    test_list = helper.list_children_ous(parent_id=parent_id)
    assert "ou-test-2" in test_list and "ou-test-3" in test_list


def test_tags_to_dict():
    """Test tags_to_dict method"""
    test_tags = [{"Key": "tag1", "Value": "value1"}]
    test_dict = helper.tags_to_dict(test_tags)
    assert test_dict == {"tag1": "value1"}


def test_codepipeline_get_status(stubbed_get_codepipeline_execution):
    """Test codepipeline_get_status method"""
    helper_class = helper.HelperCodePipeline(
        "testPipeline", stubbed_get_codepipeline_execution
    )
    test_status = helper_class.status("testPipelineExecutionId")
    assert test_status == "Succeeded"


def test_get_codepipeline(mocked_codepipeline_client):
    """Test get_codepipeline method"""
    helper_class = helper.HelperCodePipeline(
        "test-pipeline", mocked_codepipeline_client
    )
    assert helper_class.get()["pipeline"]["name"] == "test-pipeline"


def test_get_codepipeline_no_pipeline(mocked_codepipeline_client):
    """Test get_codepipeline method"""
    helper_class = helper.HelperCodePipeline(
        "fake-pipeline", mocked_codepipeline_client
    )
    with pytest.raises(mocked_codepipeline_client.exceptions.PipelineNotFoundException):
        helper_class.get()


def test_other_running_executions(stubbed_list_codepipeline_running_executions):
    """Test get_codepipeline_execution method"""
    helper_class = helper.HelperCodePipeline(
        "testPipeline", stubbed_list_codepipeline_running_executions
    )
    running_executions = helper_class.other_running_executions()
    assert len(running_executions) == 1
    assert running_executions[0]["pipelineExecutionId"] == "testPipelineExecution123"


def test_start_pipeline_execution(stubbed_start_pipeline_execution):
    """Test start_pipeline_execution method"""
    helper_class = helper.HelperCodePipeline(
        "testPipeline", stubbed_start_pipeline_execution
    )
    test_execution = helper_class.start_execution()
    assert test_execution == "testPipelineExecution123"


def test_decomission_process_running(stubbed_list_builds_and_batch_get):
    """Test get_codepipeline_execution method"""
    running_executions = helper.decommission_process_running(
        cb_client=stubbed_list_builds_and_batch_get
    )
    assert len(running_executions) == 1
    assert running_executions[0]["id"] == "testBuildId2"


def test_status_with_exception(aws_credentials):
    """Test get_codepipeline_execution method"""
    cp_client = boto3.client("codepipeline")
    with patch(
        "app.lambda_src.stepfunction.CreateAccount.helper.HelperCodePipeline.cp_client.get_pipeline_execution",
        side_effect=cp_client.exceptions.PipelineExecutionNotFoundException(
            operation_name="get_pipeline_execution",
            error_response={"Error": {"Code": "PipelineExecutionNotFoundException"}},
        ),
    ):
        cp_helper = helper.HelperCodePipeline("testPipeline")

        with pytest.raises(cp_client.exceptions.PipelineExecutionNotFoundException):
            cp_helper.status(
                execution_id="18b2c6da-2625-4b2e-a518-985884ea6ad2", max_attempts=1
            )


BASE_ACCOUNT_CONFIG_TEXT = """
mandatoryAccounts:
  # We recommend you do not change mandatory account names. These are used within Landing Zone Accelerator to reference the accounts from other config files.
  # The "name" value does not currently support spaces
  # The "name" value DOES NOT need to match the account name
  - name: Management
    description: The management (primary) account. Do not change the name field for this mandatory account. Note, the account name key does not need to match the AWS account name.
    email: <landing-zone-management-email@example.com> <----- UPDATE EMAIL ADDRESS
    organizationalUnit: Root
  - name: LogArchive
    description: The log archive account. Do not change the name field for this mandatory account. Note, the account name key does not need to match the AWS account name.
    email: <govCloud-log-archive-email@example.com> <----- UPDATE EMAIL ADDRESS
    organizationalUnit: Security
  - name: Audit
    description: The security audit account (also referred to as the audit account). Do not change the name field for this mandatory account. Note, the account name key does not need to match the AWS account name.
    email: <govCloud-audit-email@example.com> <----- UPDATE EMAIL ADDRESS
    organizationalUnit: Security
workloadAccounts:
  # The "name" will be used to set the AWS Account name
  # The "name" value does not currently support spaces
  # The "name" value DOES NOT need to match the account name
  - name: SharedServices
    description: Shared services account for GovCloud.
    email: <govCloud-shared-services-email@example.com> <----- UPDATE EMAIL ADDRESS
    organizationalUnit: Infrastructure
  - name: Network
    description: Network account for GovCloud.
    email: <govCloud-network-email@example.com> <----- UPDATE EMAIL ADDRESS
    organizationalUnit: Infrastructure

# This section enables LZA to invite the accounts into the Organizations
accountIds:
  - email: <landing-zone-management-email@example.com> <----- UPDATE EMAIL ADDRESS
    accountId: "000000000000 <----- UPDATE GOVCLOUD ACCOUNT ID from Commercial GovCloud mapping table"
  - email: <govCloud-log-archive-email@example.com> <----- UPDATE EMAIL ADDRESS
    accountId: "111111111111 <----- UPDATE GOVCLOUD ACCOUNT ID from Commercial GovCloud mapping table"
  - email: <govCloud-audit-email@example.com> <----- UPDATE EMAIL ADDRESS
    accountId: "222222222222 <----- UPDATE GOVCLOUD ACCOUNT ID from Commercial GovCloud mapping table"
  - email: <govCloud-shared-services-email@example.com> <----- UPDATE EMAIL ADDRESS
    accountId: "333333333333 <----- UPDATE GOVCLOUD ACCOUNT ID from Commercial GovCloud mapping table"
  - email: <govCloud-network-email@example.com> <----- UPDATE EMAIL ADDRESS
    accountId: "444444444444 <----- UPDATE GOVCLOUD ACCOUNT ID from Commercial GovCloud mapping table"
"""


def test_update_account_config_file(tmpdir):
    """Test update_account_config_file method"""

    test_file = tmpdir.join("test_file.yaml")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(BASE_ACCOUNT_CONFIG_TEXT)
    account_info = {
        "AccountName": "test_account",
        "AccountEmail": "test@example.com",
        "ManagedOrganizationalUnit": "testOU",
    }

    helper.update_account_config_file(test_file, account_info)
    with open(test_file, "r", encoding="utf-8") as f:
        account_config = yaml.safe_load(f)

    account = [
        account
        for account in account_config["workloadAccounts"]
        if account["name"] == "test_account"
    ]
    assert len(account) == 1
    assert account[0]["email"] == "test@example.com"
    assert account[0]["organizationalUnit"] == "testOU"
    assert account[0]["name"] == "test_account"
    assert account[0]["description"] == "test_account"


def test_update_account_config_force_update(tmpdir):
    """Test update_account_config_file method"""

    test_file = tmpdir.join("test_file.yaml")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(BASE_ACCOUNT_CONFIG_TEXT)
    account_info = {
        "AccountName": "SharedServices",
        "AccountEmail": "test@example.com",
        "ManagedOrganizationalUnit": "testOU",
    }

    helper.update_account_config_file(test_file, account_info, force_update=True)
    with open(test_file, "r", encoding="utf-8") as f:
        account_config = yaml.safe_load(f)

    account = [
        account
        for account in account_config["workloadAccounts"]
        if account["name"] == "SharedServices"
    ]
    assert len(account) == 1
    assert account[0]["email"] == "test@example.com"
    assert account[0]["organizationalUnit"] == "testOU"


def test_update_existing_raises_exception(tmpdir):
    """Test update_account_config_file method"""

    test_file = tmpdir.join("test_file.yaml")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(BASE_ACCOUNT_CONFIG_TEXT)
    account_info = {
        "AccountName": "SharedServices",
        "AccountEmail": "test@example.com",
        "ManagedOrganizationalUnit": "testOU",
    }

    with pytest.raises(helper.MatchingAccountNameInConfigException):
        helper.update_account_config_file(test_file, account_info)


BASE_OU_CONFIG_TEXT = """
###################################################################
# AWS Organizations and Organizational Units (OUs) Configurations #
###################################################################
enable: true
# Creating OUs
organizationalUnits:
  - name: Security
  - name: Infrastructure
  - name: TestOU
# Enabling the quarantine service control policies (SCPs)
quarantineNewAccounts:
  enable: true
  scpPolicyName: Quarantine
# Implementing service control policies
serviceControlPolicies:
  # Creating an SCP
  - name: AcceleratorGuardrails1
    description: >
      Accelerator GuardRails 1
    # Path to policy
    policy: service-control-policies/guardrails-1.json
    type: customerManaged
    # Attaching service control policy to accounts through OUs
    deploymentTargets:
      organizationalUnits:
        - Infrastructure
        - Security
  - name: AcceleratorGuardrails2
    description: >
      Accelerator GuardRails 2
    policy: service-control-policies/guardrails-2.json
    type: customerManaged
    deploymentTargets:
      organizationalUnits:
        - Infrastructure
        - Security
  - name: Quarantine
    description: >
      This SCP is used to prevent changes to new accounts until the Accelerator
      has been executed successfully.
      This policy will be applied upon account creation if enabled.
    policy: service-control-policies/quarantine.json
    type: customerManaged
    deploymentTargets:
      organizationalUnits: []

# https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_tag-policies.html
taggingPolicies: []
# https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_backup.html
backupPolicies: []
"""


def test_validate_ou_in_config(tmpdir):
    """Test validate_ou_in_config method"""

    test_file = tmpdir.join("test_file.yaml")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(BASE_OU_CONFIG_TEXT)

    assert helper.validate_ou_in_config(test_file, "TestOU") is None


def test_validate_ou_in_config_not_found(tmpdir):
    """Test validate_ou_in_config method"""

    test_file = tmpdir.join("test_file.yaml")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(BASE_OU_CONFIG_TEXT)

    with pytest.raises(helper.MissingOrganizationalUnitConfigException):
        helper.validate_ou_in_config(test_file, "NonExistentOU")
