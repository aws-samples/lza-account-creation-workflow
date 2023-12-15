# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from datetime import datetime
import uuid

from app.lambda_layer.identity_center_helper.python.identity_center_helper import (
    create_account_assignment_for_group,
    lookup_group_guid_from_sso,
    get_sso_instance_id_and_arn,
    get_permission_set_arn,
    ObjectNotFoundInIdentityCenter,
)

import botocore.session
from botocore.stub import Stubber
import pytest

sso_admin = botocore.session.get_session().create_client("sso-admin")
identitystore = botocore.session.get_session().create_client("identitystore")
sso_stubber = Stubber(sso_admin)
identity_stubber = Stubber(identitystore)

account_id = "123456789012"
permission_set_name = "test-permission-set"
group_name = "test-group"
group_guid = "test-guid"
permission_set_arn = f"arn:aws:iam::aws:policy/{permission_set_name}"

list_group_response = {
    "Groups": [
        {
            "GroupId": group_guid,
            "DisplayName": group_name,
            "ExternalIds": [
                {"Issuer": "string", "Id": "string"},
            ],
            "Description": "string",
            "IdentityStoreId": "test-identity-store-id",
        }
    ]
}

list_instances_response = {
    "Instances": [
        {
            "InstanceArn": "test-instance-arn",
            "IdentityStoreId": "test-identity-store-id",
        }
    ]
}


create_account_assignment_response = {
    "AccountAssignmentCreationStatus": {
        "Status": "SUCCEEDED",
        "RequestId": str(uuid.uuid4()),
        "FailureReason": "string",
        "TargetId": "012345678901",
        "TargetType": "AWS_ACCOUNT",
        "PermissionSetArn": permission_set_arn,
        "PrincipalType": "GROUP",
        "PrincipalId": group_guid,
        "CreatedDate": datetime(2015, 1, 1),
    }
}

create_account_assignment_expected_params = {
    "InstanceArn": "test-instance-arn",
    "TargetId": account_id,
    "TargetType": "AWS_ACCOUNT",
    "PermissionSetArn": permission_set_arn,
    "PrincipalType": "GROUP",
    "PrincipalId": group_guid,
}

list_permission_sets_response = {"PermissionSets": [permission_set_arn]}

permission_sets_expected_params = {
    "InstanceArn": "test-instance-arn",
}

describe_permission_set_response = {
    "PermissionSet": {
        "PermissionSetArn": permission_set_arn,
        "Name": permission_set_name,
        "Description": "string",
        "RelayState": "string",
        "SessionDuration": "PT1H",
        "CreatedDate": datetime(2015, 1, 1),
    }
}

describe_permission_set_expected_params = {
    "InstanceArn": "test-instance-arn",
    "PermissionSetArn": permission_set_arn,
}


def test_lookup_group_guid_from_sso(aws_credentials):
    with Stubber(identitystore) as identity_stubber:
        identity_stubber.add_response(
            "list_groups",
            list_group_response,
            {"IdentityStoreId": "test-identity-store-id"},
        )
        response = lookup_group_guid_from_sso(
            group_name, "test-identity-store-id", identitystore
        )
        assert response == group_guid


def test_lookup_group_guid_from_sso_empty(aws_credentials):
    with Stubber(identitystore) as identity_stubber:
        identity_stubber.add_response(
            "list_groups",
            list_group_response,
            {"IdentityStoreId": "test-identity-store-id"},
        )
        with pytest.raises(ObjectNotFoundInIdentityCenter):
            lookup_group_guid_from_sso(
                "a-missing-group-name", "test-identity-store-id", identitystore
            )


def test_create_account_assignment_for_group(aws_credentials):
    with Stubber(sso_admin) as sso_stubber:
        sso_stubber.add_response(
            "create_account_assignment",
            create_account_assignment_response,
            create_account_assignment_expected_params,
        )
        response = create_account_assignment_for_group(
            account_id, permission_set_arn, group_guid, "test-instance-arn", sso_admin
        )

        assert response == create_account_assignment_response


def test_get_sso_instance_id(aws_credentials):
    with Stubber(sso_admin) as sso_stubber:
        sso_stubber.add_response("list_instances", list_instances_response, {})
        id, arn = get_sso_instance_id_and_arn(sso_admin)
        assert (id, arn) == ("test-identity-store-id", "test-instance-arn")


def test_get_permission_set_arn(aws_credentials):
    with Stubber(sso_admin) as sso_stubber:
        sso_stubber.add_response(
            "list_permission_sets",
            list_permission_sets_response,
            permission_sets_expected_params,
        )
        sso_stubber.add_response(
            "describe_permission_set",
            describe_permission_set_response,
            describe_permission_set_expected_params,
        )
        arn = get_permission_set_arn(
            permission_set_name, "test-instance-arn", sso_admin
        )
        assert arn == permission_set_arn


def test_get_permission_set_arn_empty(aws_credentials):
    with Stubber(sso_admin) as sso_stubber:
        sso_stubber.add_response(
            "list_permission_sets",
            list_permission_sets_response,
            permission_sets_expected_params,
        )
        sso_stubber.add_response(
            "describe_permission_set",
            describe_permission_set_response,
            describe_permission_set_expected_params,
        )
        with pytest.raises(ObjectNotFoundInIdentityCenter):
            get_permission_set_arn(
                "a-missing-permission-set", "test-instance-arn", sso_admin
            )
