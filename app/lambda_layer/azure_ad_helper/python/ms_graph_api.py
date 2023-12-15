# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List
from msal import ConfidentialClientApplication
import requests

LOGGER = logging.getLogger()


class GraphApiRequestException(Exception):
    """Custom Exception"""


class AwsIdCenterJobLookupException(Exception):
    """Custom Exception"""


class SynchronizationJobStartException(Exception):
    """Custom Exception"""


class Method(Enum):
    """Request Method Types"""
    GET = "GET"
    POST = "POST"


@dataclass
class Group:
    """Describes required fields to create a new AD group
    """
    description: str
    display_name: str
    group_types: List[str]
    mail_enabled: bool
    mail_nickname: str
    security_enabled: bool


class MsGraphApiConnection:
    """Class for working with the Microsoft Azure Active Directory Graph API

    Attributes
    ----------
    client_id : str
        The Azure AD application's Client AD
    client_secret : str
        The secret that grants Graph API permission through the Azure AD application
    tenant_id : str
        The Azure AD tenant ID
    scope : Optional[List[str]]
        List of scopes for Graph API permission
    """
    url = 'https://graph.microsoft.com/v1.0'
    beta_url = 'https://graph.microsoft.com/beta'

    def __init__(self, client_id: str, tenant_id: str, client_secret: str, scope: Optional[List[str]] = None):
        self.__client_id = client_id
        self.__client_secret = client_secret
        self.__tenant_id = tenant_id
        if scope is None:
            scope = ['https://graph.microsoft.com/.default']
        self.__scope = scope
        self.__client = ConfidentialClientApplication(
            self.client_id,
            authority=f'https://login.microsoftonline.com/{self.tenant_id}',
            client_credential=self.__client_secret
        )
        self.__access_token = self.__get_token()
        self.__headers = {
            'Authorization': self.__access_token,
            'Content-Type': 'application/json'
        }

    @property
    def client_id(self) -> str:
        """Getter"""
        return self.__client_id

    @client_id.setter
    def client_id(self, set_client_id: str) -> None:
        """Setter"""
        self.__client_id = set_client_id

    @property
    def tenant_id(self) -> str:
        """Getter"""
        return self.__tenant_id

    @tenant_id.setter
    def tenant_id(self, set_tenant_id: str) -> None:
        """Setter"""
        self.__tenant_id = set_tenant_id

    @property
    def scope(self) -> str:
        """Getter"""
        return self.__scope

    @scope.setter
    def scope(self, set_scope: List[str]) -> None:
        """Setter"""
        self.__scope = set_scope

    @property
    def client(self) -> ConfidentialClientApplication:
        """Getter"""
        return self.__client

    def client_secret(self, set_client_secret: str) -> None:
        """Setter"""
        self.__client_secret = set_client_secret

    # client_secret is private, do not allow displaying outside of the class
    client_secret = property(None, client_secret)

    def __get_token(self) -> str:
        """Private: get token for authenticating to the Graph API"""
        _token = self.client.acquire_token_for_client(scopes=self.scope)
        return 'Bearer ' + _token['access_token']

    def request(self, path: str, method: Method, body: Optional[dict] = None, beta: Optional[bool] = False) -> requests.Response:
        """Make a request to the Graph API

        Args:
            path (str): The API path, should include leading /
            method (Method): The request method, one of GET, POST
            body (Optional[dict]): The body of the post request as a dictionary object
            beta (Optional[bool]): If the call should use the beta URL, False by default

        Raises:
            GraphApiRequestException: If an error is returned from the request

        Returns:
            requests.Response: Response object with data from the API
        """
        target_url = MsGraphApiConnection.beta_url if beta else MsGraphApiConnection.url

        if method == Method.GET:
            response = requests.get(
                url=target_url + path,
                headers=self.__headers,
                timeout=30
            )

        elif method == Method.POST:
            response = requests.post(
                url=target_url + path,
                data=json.dumps(body),
                headers=self.__headers,
                timeout=30
            )

        else:
            raise GraphApiRequestException(
                f'Invalid method {method}, unable to make request')

        LOGGER.debug('%s Request Response:', method)
        LOGGER.debug(response.text)
        try:
            if response.json().get('error'):
                raise GraphApiRequestException(
                    f'There was an error making a {method.value} request to graph API: {response.json().get("error")}')
        except ValueError as no_json_object:
            LOGGER.debug(
                'Response is text only or none, no JSON: %s', no_json_object)

        return response


class MsGraphApiGroups:
    """Class for working with groups in the Microsoft Azure Active Directory Graph API

    Attributes
    ----------
    client : MsGraphApiConnection
        The object containing the api connection with request type methods
    group_id : Optional[str]
        Optional Group ID if working with an existing group

    Raises:
        GraphApiRequestException: Exception if an error is returned when calling the API to create a group
    """

    def __init__(self, client: MsGraphApiConnection, group_id: Optional[str] = None):
        self.__client = client
        self.__group_id = group_id

    @property
    def client(self) -> MsGraphApiConnection:
        """getter"""
        return self.__client

    @client.setter
    def client(self, new_client: MsGraphApiConnection) -> None:
        """setter"""
        self.__client = new_client

    @property
    def group_id(self) -> str:
        """getter"""
        return self.__group_id

    @group_id.setter
    def group_id(self, new_group_id: str) -> None:
        """setter"""
        self.__group_id = new_group_id

    def list_existing_groups(self) -> List[dict]:
        """Get a list of JSON strings for existing groups in the Azure AD tenant"""
        return self.client.request(path='/groups', method=Method.GET).json().get('value', [])

    def create_group(self, group_info: Group) -> dict:
        """Create group in the Azure AD tenant

        Args:
            group_info(Group): Object containing the attributes for the new group

        Raises:
            GraphApiRequestException: Error from Azure AD if there is a problem creating the group

        Returns:
            dict: API response with group info
        """
        _body = {
            "description": group_info.description,
            "displayName": group_info.display_name,
            "groupTypes": group_info.group_types,
            "mailEnabled": group_info.mail_enabled,
            "mailNickname": group_info.mail_nickname,
            "securityEnabled": group_info.security_enabled
        }

        _new_group = self.client.request(
            path='/groups',
            method=Method.POST,
            body=_body
        )

        self.group_id = _new_group.json()['id']
        return _new_group

    def add_group_to_sso(self, app_object_id: str, app_role_id: str) -> requests.Response:
        """Add a group to the given enterprise application role. To be used
        for adding the group to the SSO Identity Center Azure Application
        for syncing the new group to AWS Identity Center

        Args:
            app_object_id (str): The Object ID for the Identity Center Azure AD Enterprise App
            app_role_id (str): The role ID for the User role within the Identity Center Azure AD Enterprise App

        Returns:
            dict: API Response dictionary
        """
        _body = {
            "principalId": self.group_id,
            "resourceId": app_object_id,
            "appRoleId": app_role_id
        }

        _response = self.client.request(
            path=f"/groups/{self.group_id}/appRoleAssignments",
            method=Method.POST,
            body=_body
        )

        return _response

    def get_group_info_from_name(self, group_name: str) -> dict:
        """Attempt to get information for group from the group name and
        sets the current object's group ID to the looked up value

        Args:
            group_name (str): The display name of the Azure AD group

        Returns:
            dict: The Azure AD group information as a dictionary
        """
        _all_groups = self.list_existing_groups()
        _group_lookup = next(iter([group for group in _all_groups if group['displayName'].lower() == group_name.lower()]), {})
        self.group_id = _group_lookup['id']
        return _group_lookup


@dataclass
class Synchronizer:
    """Class to run synchronization from Azure AD to AWS Identity Center"""
    api_connection: MsGraphApiConnection
    aws_identity_center_object_id: str
    beta: bool = True

    def sync_azure_ad_aws_identity_center(self) -> None:
        """Start a synchronization job of the AWS Identity Center application in Azure AD to
        sync AD users and groups to AWS

        Attributes:
        ----------
        api_connection : MsGraphApiConnection
            The connection object for Azure Graph API

        Raises:
            SynchronizationJobStartException: If no job ID is found for synchronization for the object ID passed in for AWS ID Center App
        """
        _jobs_response = self.api_connection.request(
            f'/servicePrincipals/{self.aws_identity_center_object_id}/synchronization/jobs', method=Method.GET, beta=self.beta).json()
        try:
            _job_id = next(iter(_jobs_response.get('value', {}))).get('id')
        except StopIteration as no_jobs_found:
            raise self.__raise_job_exception() from no_jobs_found
        if _job_id is None:
            raise self.__raise_job_exception()

        _start_sync = self.api_connection.request(
            f'/servicePrincipals/{self.aws_identity_center_object_id}/synchronization/jobs/{_job_id}/start', body={}, method=Method.POST, beta=self.beta)

        _status = _start_sync.status_code
        LOGGER.info('Status code: %s', _status)
        if _status not in [200, 204, "200", "204"]:
            raise SynchronizationJobStartException(
                f'There was an error starting the synchronization of AWS Identity Center from Azure, status code returned {_status} for job ID {_job_id}')

        LOGGER.info(
            'Successfully started sync of Azure AD to AWS Identity Center')

    def __raise_job_exception(self) -> AwsIdCenterJobLookupException:
        """Raise custom exception"""
        return AwsIdCenterJobLookupException(
            f'No jobs were found for service principal: {self.aws_identity_center_object_id}')
