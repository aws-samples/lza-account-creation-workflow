# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from app.lambda_src.stepfunction.CreateAccount import helper
import pytest


def test_build_root_email_address(monkeypatch):
    monkeypatch.setenv("ROOT_EMAIL_PREFIX", "pytest")
    monkeypatch.setenv("ROOT_EMAIL_DOMAIN", "example.com")
    test_root_email = helper.build_root_email_address("test-account1")
    assert test_root_email == "pytest+test-account1@example.com"


def test_build_root_email_with_extra_chars(monkeypatch):
    monkeypatch.setenv("ROOT_EMAIL_PREFIX", "pytest")
    monkeypatch.setenv("ROOT_EMAIL_DOMAIN", "@example.com")
    test_root_email = helper.build_root_email_address("test account 1")
    assert test_root_email == "pytest+test-account-1@example.com"


def test_raises_exception(monkeypatch):
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
