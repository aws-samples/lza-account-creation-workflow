# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0


from app.lambda_layer.azure_ad_helper.python.ms_graph_api import (
    GraphApiRequestException,
    Group,
    MsGraphApiConnection,
    MsGraphApiGroups,
    Method,
    Synchronizer,
    AwsIdCenterJobLookupException,
    SynchronizationJobStartException,
)
from app.lambda_src.stepfunction.AzureADGroupSync.helpers import get_secret_value
from app.lambda_src.stepfunction.AzureADGroupSync.main import lambda_handler

import json
# import requests
from dataclasses import dataclass
from typing import List
from unittest.mock import patch

# import boto3
import pytest

from moto import mock_secretsmanager
from moto.secretsmanager.models import secretsmanager_backends
from moto.core import DEFAULT_ACCOUNT_ID

import pprint
import sys

pprint.pprint(sys.path)


@pytest.fixture
def get_mocked_msal_creds():
    return MockedMsalCredentials


@dataclass
class MockedMsalCredentials:
    client_id: str
    authority: str
    client_credentials: str

    def acquire_token_for_client(scopes: List[str]) -> dict:
        return {"access_token": "faketokenfortesting"}


def test_create_group_settings_object():
    test_group = Group(
        description="test",
        display_name="test",
        group_types=["Universal"],
        mail_enabled=True,
        mail_nickname="test",
        security_enabled=True,
    )
    assert test_group
    assert test_group.group_types == ["Universal"]


@pytest.fixture
def mocked_secrets(aws_credentials):
    with mock_secretsmanager():
        sm_backend = secretsmanager_backends[DEFAULT_ACCOUNT_ID]["us-east-1"]
        sm_backend.create_secret(       # nosec B106 - this is a unit test, no secrets are being stored
            name="testing/graph-api",
            secret_string='{"client_id": "test_cid", "tenant_id": "test_tid", "secret_value": "test_secret_key", "object_id": "app_obj_id", "app_role_id": "app_role_id"}',
        )
        yield sm_backend


def test_retrieve_ssm_secret_value(mocked_secrets):
    api_secrets = json.loads(get_secret_value("testing/graph-api"))
    assert api_secrets["client_id"] == "test_cid"
    assert api_secrets["tenant_id"] == "test_tid"
    assert api_secrets["secret_value"] == "test_secret_key"
    assert api_secrets["object_id"] == "app_obj_id"
    assert api_secrets["app_role_id"] == "app_role_id"


@patch(
    "app.lambda_layer.azure_ad_helper.python.ms_graph_api.ConfidentialClientApplication",
    return_value=MockedMsalCredentials,
    autospec=True,
)
def test_create_api_object(get_mocked_msal_creds):
    test_api = MsGraphApiConnection("client_id", "client_secret", "tenant_id")
    assert test_api.client_id == "client_id"
    assert test_api._MsGraphApiConnection__access_token == "Bearer faketokenfortesting"  # nosec B105 - this is a unit test, no secrets are being stored
    assert test_api.scope == ["https://graph.microsoft.com/.default"]
    test_api.client_id = "new_cid"
    assert test_api.client_id == "new_cid"
    test_api.tenant_id = "new_tid"
    assert test_api.tenant_id == "new_tid"
    test_api.client_secret = "new_secret"   # nosec B105 - this is a unit test, no secrets are being stored 
    assert test_api._MsGraphApiConnection__client_secret == "new_secret"    # nosec B105 - this is a unit test, no secrets are being stored
    test_api.scope = ["users.read"]
    assert test_api.scope == ["users.read"]
    assert test_api.client.acquire_token_for_client(["scope"]) == {
        "access_token": "faketokenfortesting"
    }


@patch(
    "app.lambda_layer.azure_ad_helper.python.ms_graph_api.ConfidentialClientApplication",
    return_value=MockedMsalCredentials,
    autospec=True,
)
def test_client_secret_is_private(get_mocked_msal_creds):
    test_api = MsGraphApiConnection("client_id", "client_secret", "tenant_id")
    with pytest.raises(AttributeError) as att_error:
        test_api.client_secret
        assert str(att_error) == "unreadable attribute"


@patch(
    "app.lambda_layer.azure_ad_helper.python.ms_graph_api.ConfidentialClientApplication",
    return_value=MockedMsalCredentials,
    autospec=True,
)
def test_create_group_obj(get_mocked_msal_creds, requests_mock):
    test_group = MsGraphApiGroups(
        MsGraphApiConnection("client_id", "tenant_id", "client_secret")
    )
    assert test_group.group_id is None
    assert test_group.client.client_id == "client_id"
    test_group.group_id = "12345"
    test_group.client = MsGraphApiConnection("cid", "tid", "cid2")
    assert test_group.group_id == "12345"
    assert test_group.client.client_id == "cid"


@patch(
    "app.lambda_layer.azure_ad_helper.python.ms_graph_api.ConfidentialClientApplication",
    return_value=MockedMsalCredentials,
    autospec=True,
)
def test_list_existing_groups(get_mocked_msal_creds, requests_mock):
    requests_mock.get(      # nosec B113 - This is a mock request with no timeout arguement
        "https://graph.microsoft.com/v1.0/groups",
        text='{"value": [{"GroupName": "test"}]}',
    )
    test_api = MsGraphApiGroups(
        MsGraphApiConnection("client_id", "tenant_id", "client_secret")
    )
    assert test_api.list_existing_groups() == [{"GroupName": "test"}]
    requests_mock.get(      # nosec B113 - This is a mock request with no timeout arguement
        "https://graph.microsoft.com/v1.0/groups", 
        text="{}"
    )
    assert test_api.list_existing_groups() == []


@patch(
    "app.lambda_layer.azure_ad_helper.python.ms_graph_api.ConfidentialClientApplication",
    return_value=MockedMsalCredentials,
    autospec=True,
)
def test_create_group(get_mocked_msal_creds, requests_mock):
    requests_mock.post(     # nosec B113 - This is a mock request with no timeout arguement
        "https://graph.microsoft.com/v1.0/groups",
        text='{"GroupName": "NewGroup", "id": "12345"}',
    )
    requests_mock.post(     # nosec B113 - This is a mock request with no timeout arguement
        "https://graph.microsoft.com/v1.0/groups/12345/appRoleAssignments",
        text='{"GroupName": "NewGroup", "id": "12345"}',
    )
    test_api = MsGraphApiGroups(
        MsGraphApiConnection("client_id", "tenant_id", "client_secret")
    )
    new_test_group_info = Group(
        description="test",
        display_name="test",
        group_types=["Universal"],
        mail_enabled=True,
        mail_nickname="test",
        security_enabled=True,
    )
    new_test_group = test_api.create_group(new_test_group_info)
    assert new_test_group.json() == {"GroupName": "NewGroup", "id": "12345"}
    assert test_api.group_id == "12345"


@patch(
    "app.lambda_layer.azure_ad_helper.python.ms_graph_api.ConfidentialClientApplication",
    return_value=MockedMsalCredentials,
    autospec=True,
)
def test_create_group_error(get_mocked_msal_creds, requests_mock):
    requests_mock.post(     # nosec B113 - This is a mock request with no timeout arguement
        "https://graph.microsoft.com/v1.0/groups",
        text='{"error": "there was a problem"}',
    )
    requests_mock.post(     # nosec B113 - This is a mock request with no timeout arguement
        "https://graph.microsoft.com/v1.0/groups/12345/appRoleAssignments",
        text='{"GroupName": "NewGroup", "id": "12345"}',
    )
    test_api = MsGraphApiGroups(
        MsGraphApiConnection("client_id", "client_secret", "tenant_id")
    )
    new_test_group_info = Group(
        description="test",
        display_name="test",
        group_types=["Universal"],
        mail_enabled=True,
        mail_nickname="test",
        security_enabled=True,
    )
    with pytest.raises(GraphApiRequestException) as group_except:
        test_api.create_group(new_test_group_info)
        assert (
            str(group_except)
            == "There was an error making a GET request: there was a problem"
        )


@patch(
    "app.lambda_layer.azure_ad_helper.python.ms_graph_api.ConfidentialClientApplication",
    return_value=MockedMsalCredentials,
    autospec=True,
)
def test_handle_request_response_without_json(get_mocked_msal_creds, requests_mock):
    requests_mock.get(      # nosec B113 - This is a mock request with no timeout arguement
        "https://graph.microsoft.com/v1.0/an_endpoint", 
        text="hello"
    )
    con = MsGraphApiConnection("client_id", "tenant_id", "client_secret")
    response = con.request("/an_endpoint", Method.GET)
    assert response.text == "hello"
    with pytest.raises(ValueError):
        response.json()


@patch(
    "app.lambda_layer.azure_ad_helper.python.ms_graph_api.ConfidentialClientApplication",
    return_value=MockedMsalCredentials,
    autospec=True,
)
def test_synchronizer_raises_no_job_exception(get_mocked_msal_creds, requests_mock):
    conn = MsGraphApiConnection("client_id", "tenant_id", "client_secret")
    sync = Synchronizer(conn, "obj_id")
    requests_mock.get(      # nosec B113 - This is a mock request with no timeout arguement
        "https://graph.microsoft.com/beta/servicePrincipals/obj_id/synchronization/jobs",
        text='{"value": []}',
    )
    with pytest.raises(AwsIdCenterJobLookupException):
        sync.sync_azure_ad_aws_identity_center()
    requests_mock.get(      # nosec B113 - This is a mock request with no timeout arguement
        "https://graph.microsoft.com/beta/servicePrincipals/obj_id/synchronization/jobs",
        text='{"value": [{"something": "unexpected"}]}',
    )
    with pytest.raises(AwsIdCenterJobLookupException):
        sync.sync_azure_ad_aws_identity_center()


@patch(
    "app.lambda_layer.azure_ad_helper.python.ms_graph_api.ConfidentialClientApplication",
    return_value=MockedMsalCredentials,
    autospec=True,
)
def test_synchronizer_raises_bad_status(get_mocked_msal_creds, requests_mock):
    conn = MsGraphApiConnection("client_id", "tenant_id", "client_secret")
    sync = Synchronizer(conn, "obj_id")
    requests_mock.get(      # nosec B113 - This is a mock request with no timeout arguement
        "https://graph.microsoft.com/beta/servicePrincipals/obj_id/synchronization/jobs",
        text='{"value": [{"id": "1234"}]}',
    )
    requests_mock.post(     # nosec B113 - This is a mock request with no timeout arguement
        "https://graph.microsoft.com/beta/servicePrincipals/obj_id/synchronization/jobs/1234/start",
        text="",
        status_code=503,
    )
    requests_mock.get(      # nosec B113 - This is a mock request with no timeout arguement
        "https://login.microsoftonline.com:443/test_tid/v2.0/.well-known/openid-configuration",
        text=json.dumps(mocked_auth_response),
    )
    with pytest.raises(SynchronizationJobStartException):
        sync.sync_azure_ad_aws_identity_center()


@patch(
    "app.lambda_layer.azure_ad_helper.python.ms_graph_api.ConfidentialClientApplication",
    return_value=MockedMsalCredentials,
    autospec=True,
)
def test_lambda_payload(
    get_mocked_msal_creds, requests_mock, mocked_secrets, monkeypatch
):
    requests_mock.get(      # nosec B113 - This is a mock request with no timeout arguement
        "https://graph.microsoft.com/v1.0/groups",
        text='{"value":[{"displayName": "test-group", "id": "12345"}]}',
    )
    requests_mock.post(     # nosec B113 - This is a mock request with no timeout arguement
        "https://graph.microsoft.com/v1.0/groups/12345/appRoleAssignments",
        text='{"GroupName": "NewGroup", "id": "12345"}',
    )
    requests_mock.get(      # nosec B113 - This is a mock request with no timeout arguement
        "https://login.microsoftonline.com:443/test_tid/v2.0/.well-known/openid-configuration",
        text=json.dumps(mocked_auth_response),
    )
    requests_mock.post(     # nosec B113 - This is a mock request with no timeout arguement
        "https://login.microsoftonline.com/test_tid/oauth2/v2.0/token",
        text='{"access_token":"afaketoken"}',
    )
    requests_mock.get(      # nosec B113 - This is a mock request with no timeout arguement
        "https://graph.microsoft.com/beta/servicePrincipals/app_obj_id/synchronization/jobs",
        text='{"value":[{"id":"jjjjj"}]}',
    )
    requests_mock.post(     # nosec B113 - This is a mock request with no timeout arguement
        "https://graph.microsoft.com/beta/servicePrincipals/app_obj_id/synchronization/jobs/jjjjj/start",
        text="{}",
    )
    requests_mock.get(      # nosec B113 - This is a mock request with no timeout arguement
        "https://login.microsoftonline.com/test_tid/v2.0/.well-known/openid-configuration",
        text=json.dumps(mocked_auth_response),
    )
    monkeypatch.setenv("GRAPH_API_SECRET_NAME", "testing/graph-api")
    event = {
        "Payload": {
            "AccountInfo": {
                "AccountName": "pytest",
                "ADIntegration": {"test-permission-set": "test-group"},
            },
            "Account": {"Outputs": {"AccountId": DEFAULT_ACCOUNT_ID}},
        }
    }
    payload = lambda_handler(event, {})
    assert payload["AccountInfo"]["ADIntegration"] == {
        "test-permission-set": "test-group"
    }
    assert payload["Account"]["Outputs"]["AccountId"] == DEFAULT_ACCOUNT_ID


@patch(
    "app.lambda_layer.azure_ad_helper.python.ms_graph_api.ConfidentialClientApplication",
    return_value=MockedMsalCredentials,
    autospec=True,
)
def test_create_group_error_in_lambda(
    get_mocked_msal_creds, requests_mock, mocked_secrets, monkeypatch
):
    requests_mock.post(     # nosec B113 - This is a mock request with no timeout arguement
        "https://graph.microsoft.com/v1.0/groups",
        text='{"error": "there was a problem"}',
    )
    requests_mock.post(     # nosec B113 - This is a mock request with no timeout arguement
        "https://graph.microsoft.com/v1.0/groups/12345/appRoleAssignments",
        text='{"GroupName": "NewGroup", "id": "12345"}',
    )
    requests_mock.get(      # nosec B113 - This is a mock request with no timeout arguement
        "https://graph.microsoft.com/beta/servicePrincipals/app_obj_id/synchronization/jobs",
        text='{"value":[{"id":"jjjjj"}]}',
    )
    event = {
        "Payload": {
            "AccountInfo": {
                "AccountName": "pytest",
                "ADIntegration": {"test-permission-set": "test-group"},
            },
            "Account": {"Outputs": {"AccountId": DEFAULT_ACCOUNT_ID}},
        }
    }
    monkeypatch.setenv("GRAPH_API_SECRET_NAME", "testing/graph-api")

    with pytest.raises(TypeError):
        lambda_handler(event, {})


mocked_auth_response = {
    "token_endpoint": "https://login.microsoftonline.com/test_tid/oauth2/v2.0/token",
    "token_endpoint_auth_methods_supported": [
        "client_secret_post",
        "private_key_jwt",
        "client_secret_basic",
    ],
    "jwks_uri": "https://login.microsoftonline.com/test_tid/discovery/v2.0/keys",
    "response_modes_supported": ["query", "fragment", "form_post"],
    "subject_types_supported": ["pairwise"],
    "id_token_signing_alg_values_supported": ["RS256"],
    "response_types_supported": ["code", "id_token", "code id_token", "id_token token"],
    "scopes_supported": ["openid", "profile", "email", "offline_access"],
    "issuer": "https://login.microsoftonline.com/test_tid/v2.0",
    "request_uri_parameter_supported": False,
    "userinfo_endpoint": "https://graph.microsoft.com/oidc/userinfo",
    "authorization_endpoint": "https://login.microsoftonline.com/test_tid/oauth2/v2.0/authorize",
    "device_authorization_endpoint": "https://login.microsoftonline.com/test_tid/oauth2/v2.0/devicecode",
    "http_logout_supported": True,
    "frontchannel_logout_supported": True,
    "end_session_endpoint": "https://login.microsoftonline.com/test_tid/oauth2/v2.0/logout",
    "claims_supported": [
        "sub",
        "iss",
        "cloud_instance_name",
        "cloud_instance_host_name",
        "cloud_graph_host_name",
        "msgraph_host",
        "aud",
        "exp",
        "iat",
        "auth_time",
        "acr",
        "nonce",
        "preferred_username",
        "name",
        "tid",
        "ver",
        "at_hash",
        "c_hash",
        "email",
    ],
    "kerberos_endpoint": "https://login.microsoftonline.com/test_tid/kerberos",
    "tenant_region_scope": "NA",
    "cloud_instance_name": "microsoftonline.com",
    "cloud_graph_host_name": "graph.windows.net",
    "msgraph_host": "graph.microsoft.com",
    "rbac_url": "https://pas.windows.net",
}
