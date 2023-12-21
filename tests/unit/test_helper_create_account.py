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
    "stubbed_servicecatalog_client", ["testProduct"], indirect=True
)
def test_get_provisioning_artifact_id(stubbed_servicecatalog_client):
    """Test the get_provisioning_artifact_id funciton using botocore Stubber"""
    test_product_id = helper.get_provisioning_artifact_id(
        "testProduct", stubbed_servicecatalog_client
    )
    assert test_product_id == "testId1"


@pytest.mark.parametrize(
    "stubbed_servicecatalog_client", ["fakeProduct"], indirect=True
)
def test_get_provisioning_artifact_id_no_product(stubbed_servicecatalog_client):
    """Test the get_provisioning_artifact_id funciton using botocore Stubber"""
    with pytest.raises(KeyError):
        helper.get_provisioning_artifact_id(
            "fakeProduct", stubbed_servicecatalog_client
        )
