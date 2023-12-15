# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from app.lambda_src.stepfunction.ValidateResources.validate_tags import (
    ValidateAccountTags,
    AccountTagsValidationException,
)

from moto.core import DEFAULT_ACCOUNT_ID
import pytest


def test_response_correct_tags(organizations_client, mocked_organization):
    """Happy path test for validation"""
    tag_validator = ValidateAccountTags(
        account_id=DEFAULT_ACCOUNT_ID,
        tags=[{"Key": "Owner", "Value": "Tester McTest"}],
        org_client=organizations_client,
    )
    assert tag_validator.validate() == {
        "Service": "AccountTagsValidation",
        "Status": "Succeeded",
        "Message": f"Existing tags match expected tags for account {DEFAULT_ACCOUNT_ID}",
    }


def test_error_incorrect_tags(organizations_client, mocked_organization):
    """Test error is raised when tags don't match"""
    tag_validator = ValidateAccountTags(
        account_id=DEFAULT_ACCOUNT_ID,
        tags=[{"Key": "Email", "Value": "Tester_McTest@email.com"}],
        org_client=organizations_client,
    )
    with pytest.raises(AccountTagsValidationException) as acct_valid_exc:
        tag_validator.validate()
    assert (
        str(acct_valid_exc.value)
        == "The existing tags and expected tags do not match.\n\tExisting tags: [{'Key': 'Owner', 'Value': 'Tester McTest'}]\n\tExpected tags: [{'Key': 'Email', 'Value': 'Tester_McTest@email.com'}]\n\tDifference: [{'Key': 'Owner', 'Value': 'Tester McTest'}, {'Key': 'Email', 'Value': 'Tester_McTest@email.com'}]\n"
    )
