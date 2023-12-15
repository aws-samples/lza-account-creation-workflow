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
