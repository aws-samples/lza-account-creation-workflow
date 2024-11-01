# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import copy
import logging
import zipfile
from dataclasses import dataclass
from time import sleep
import yaml
import boto3

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


class MatchingAccountNameInConfigException(Exception):
    """Custom Exception"""


class MissingOrganizationalUnitConfigException(Exception):
    """Custom Exception"""


class MissingEnvironmentVariableException(Exception):
    """Custom Exception"""


def check_delay() -> int:
    """Helper to retrieve default delay for polling.
    
    Returns:
        int: Default delay in seconds
    """

    return 5


def build_service_catalog_parameters(parameters: dict) -> list:
    """Updates the format of the parameters to allow Service Catalog to consume them

    Args:
        parameters (dict): List of parameters in the format of
            {"key1":"value1", "key2":"value2"}

    Returns:
        list: Parameters in the format of {"Key":"string", "Value":"string"}
    """
    new_parameters = []
    for key, value in parameters.items():
        y = {"Key": key, "Value": value}
        new_parameters.append(y)
    return new_parameters


def get_provisioning_artifact_id(product_name: str, client: boto3.client) -> str:
    """Retrieve the Default Service Catalog Provisioning Artifact ID from the Service Catalog Product specified in
    the definition call.

    Args:
        product_name (str): Service Catalog Product Name
        client (boto3.client): Boto3 Client for Service Catalog

    Returns:
        str: Service Catalog Provisioning Artifact ID

    Raises:
        KeyError: If no default artifact is found
    """
    product_info = client.describe_product(Name=product_name)
    LOGGER.info(product_info)

    for _product_info in product_info["ProvisioningArtifacts"]:
        if _product_info["Guidance"] == "DEFAULT":
            LOGGER.info("Found ProvisioningArtifactId:%s", _product_info['Id'])
            return _product_info["Id"]


def create_update_provision_product(
    product_name: str,
    pp_name: str,
    pa_id: str,
    client: boto3.client,
    params: list,
    update: str,
    tags=None,
) -> dict:
    """Creates a Service Catalog Provisioned Product

    Args:
        product_name (str): Service Catalog Product Name
        pp_name (str): Service Catalog Provisioned Product Name
        pa_id (str): Service Catalog Provisioned Artifact ID
        client (boto3.client): Boto3 Client for Service Catalog
        params (list): List of Service Catalog Provisioned Product Parameters
        tags (list): List of tags to add to the Service Catalog Provisioned Product
        update (bool) = Does the product need to be updated?

    Returns:
        Return: boto3.client response for service catalog provision product
    """
    param_tags = copy.deepcopy(params)

    # Since there can't be any () within a tag, so we remove them and add a : between the OU name and OU id
    # Prefixing SCParameter on all Service Catalog Provisioned Product Parameters
    for d in param_tags:
        d.update(
            (k, v.replace(" ", ":").replace("(", "").replace(")", ""))
            for k, v in d.items()
            if ("(" and ")") in v
        )
        d.update((k, f"SCParameter:{v}") for k, v in d.items() if k == "Key")

    if tags:
        for x in param_tags:
            tags.append(x)
    else:
        tags = param_tags

    LOGGER.debug("Parameters used:%s", params)
    LOGGER.debug("product_name:%s", product_name)
    LOGGER.debug("pp_name:%s", pp_name)
    LOGGER.debug("pa_id:%s", pa_id)
    LOGGER.debug("params:%s", params)
    LOGGER.debug("tags:%s", tags)

    if update == "true":
        LOGGER.info(
            "Updating pp_id:%s with ProvisionArtifactId:%s in ProductName:%s",
            pp_name, pa_id, product_name
        )
        sc_response = client.update_provisioned_product(
            ProductName=product_name,
            ProvisionedProductName=pp_name,
            ProvisioningArtifactId=pa_id,
            ProvisioningParameters=params,
            Tags=tags,
        )
    else:
        LOGGER.info(
            "Creating pp_id:%s with ProvisionArtifactId:%s in ProductName:%s",
            pp_name, pa_id, product_name
        )
        sc_response = client.provision_product(
            ProductName=product_name,
            ProvisionedProductName=pp_name,
            ProvisioningArtifactId=pa_id,
            ProvisioningParameters=params,
            Tags=tags,
        )
    LOGGER.debug(sc_response)
    return sc_response


def list_children_ous(parent_id: str):
    """Lists the organizational units (OUs) that are children of the given parent ID.

    Args:
        parent_id (str): The ID of the parent OU or account to list children for.

    Returns:
        dict: A dictionary mapping child OU names to IDs.
    """
    ou_info = {}
    org = boto3.client("organizations")
    LOGGER.info("Getting Children Ous for Id: %s", parent_id)
    list_child_paginator = org.get_paginator("list_organizational_units_for_parent")
    for _org_info in list_child_paginator.paginate(ParentId=parent_id):
        for __org_info in _org_info["OrganizationalUnits"]:
            ou_info.update({__org_info["Name"]: __org_info["Id"]})

    LOGGER.info("Found OU ID: %s", ou_info)
    return ou_info


def tags_to_dict(tags):
    """Helper for converting the tag structure Boto3 returns into a python dict

    Args:
        tags (list of dict): Tag structure returned from an AWS call

    Returns:
        dict: Tags mapped from tag name to tag value
    """
    output = {}
    if tags:
        LOGGER.debug("Found tags: %s", tags)
        for tag in tags:
            output[tag["Key"]] = tag["Value"]

    return output


def update_account_config_file(
    path_to_file: str, account_info: dict, force_update: bool = False
) -> None:
    """Update LZA account config file with account info if not already present
    

    Args:
        path_to_file (str): Path to the account-config.yaml file to update
        account_info (dict): Account Information with name, email, sso name, sso email, and target OU
        force_update (bool): This will force an update to the account-config.yaml file
    """
    with open(path_to_file, encoding="utf8") as acct_config_file:
        account_config = yaml.safe_load(acct_config_file)

    config_info = {
        "name": account_info["AccountName"],
        "description": account_info["AccountName"],
        "email": account_info["AccountEmail"],
        "organizationalUnit": account_info["ManagedOrganizationalUnit"],
    }

    update_index = -1
    for index, item in enumerate(account_config["workloadAccounts"]):
        if item["name"] == config_info["name"]:
            update_index = index

    if update_index >= 0 and force_update:
        LOGGER.info(
            "Account with name of %s already exists in config: %s",
            config_info["name"],
            account_config["workloadAccounts"][update_index],
        )
        LOGGER.info(
            "Force update is set to True, overwriting existing account info with the newly provided info"
        )
        account_config["workloadAccounts"][update_index] = config_info
    elif update_index >= 0 and not force_update:
        LOGGER.info(
            "Account with name of %s already exists in config: %s",
            config_info["name"],
            account_config["workloadAccounts"][update_index],
        )
        LOGGER.error(
            "Force update is set to False, raising exception, please investigate if this existing "
            "config should be updated or the account name should be changed in the new creation"
        )
        raise MatchingAccountNameInConfigException(
            "The accounts-config.yaml already contains an account with the name of "
            f"{config_info['name']} and the force update flag is set to False"
        )
    else:
        account_config["workloadAccounts"].append(config_info)

    with open(path_to_file, "w", encoding="utf8") as acct_config_file:
        yaml.dump(account_config, acct_config_file)


def validate_ou_in_config(path_to_file: str, target_ou_name: str) -> None:
    """Raises exception if the OU for the account config is not in the organization config

    Args:
        path_to_file (str): Path to organization-config.yaml file or other name
        target_ou_name (str): Target OU for the account creation

    Returns:
        None
        
    Raises:
        MissingOrganizationalUnitConfigException: If OU not found
    """
    with open(path_to_file, encoding="utf8") as org_config_file:
        org_config = yaml.safe_load(org_config_file)

    config_orgs = [org["name"] for org in org_config["organizationalUnits"]]

    if target_ou_name not in config_orgs:
        raise MissingOrganizationalUnitConfigException(
            f"The target OU of {target_ou_name} for account creation is not found in the current "
            f"organization-config.yaml: {org_config}. Please investigate and either fix account "
            "config or add the OU to the organization config."
        )


def build_root_email_address(account_name: str) -> str:
    """Build the root email address from prefix and domain
    
    Args:
        account_name (str): The name of the account being created

    Returns:
        str: The email to be used as the root address for the new account

    Raises:
       MissingEnvironmentVariableException: If the prefix or domain environment vars are missing
        
    Builds root email from env vars and account name. Removes spaces 
        and special characters.
    """
    try:
        prefix = os.environ["ROOT_EMAIL_PREFIX"]
        domain = os.environ["ROOT_EMAIL_DOMAIN"]
        domain = domain.replace("@", "")
        account_name = account_name.replace(" ", "-")
        root_email = f"{prefix}+{account_name}@{domain}"
        LOGGER.info("Built root account email address as: %s", root_email)
        return root_email

    except KeyError as key_error:
        raise MissingEnvironmentVariableException(
            f"The environment variable {str(key_error)} was not found but is required"
        ) from key_error


def decommission_process_running(
    project_name: str = "lzac-account-decommission", cb_client: boto3.client = None
) -> list:
    """Checks to see if the decommission CodeBuild project is running
    
    Args:
        project_name (str): CodeBuild Project that runs the decommissioning script

    Returns:
        list: Results for all IN_PROGRESS CodeBuilds jobs

    Makes CodeBuild API calls to check running builds for the project.
    """
    if not cb_client:
        cb_client = boto3.client("codebuild")
    try:
        _paginator = cb_client.get_paginator("list_builds_for_project")
        _iterator = _paginator.paginate(projectName=project_name)
        for _iter in _iterator:
            response = cb_client.batch_get_builds(ids=_iter["ids"])["builds"]
            in_progress = list(
                item for item in response if item.get("buildStatus") == "IN_PROGRESS"
            )
            LOGGER.debug("in_progress: %s", in_progress)
            return in_progress

    except Exception as err:
        LOGGER.error(err)


def zip_directory(directory_path, zip_file_name) -> str:
    """
    Zip the contents of a directory.

    Args:
        directory_path (str): The path to the directory to be zipped.
        zip_file_name (str): The name of the output zip file.

    Returns:
        str: The full path to the generated zip file.
    """
    zip_file_path = os.path.join(os.path.dirname(directory_path), zip_file_name)
    with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                zip_file.write(file_path, os.path.relpath(file_path, directory_path))

    return zip_file_path


def get_pipeline_s3_src_config(client: object, pipeline_name='AWSAccelerator-Pipeline'):
    """
    Retrieves the S3 source configuration for a specified AWS CodePipeline.

    Args:
        client (object): An AWS SDK client object with permissions to call the
                         get_pipeline API. This is typically a boto3 CodePipeline client.
        pipeline_name (str, optional): The name of the pipeline to query. 
                                       Defaults to 'AWSAccelerator-Pipeline'.

    Returns:
        tuple: A tuple containing two elements:
            - bucket (str or None): The name of the S3 bucket used as the source.
                                    None if not found.
            - object_key (str or None): The object key (path to the file) in the S3 bucket.
                                        None if not found.
    """
    bucket = None
    object_key = None

    response = client.get_pipeline(
        name=pipeline_name
    )

    if not response['pipeline']:
        raise Exception("Could not find Pipeline: %s", pipeline_name)

    for stage in response['pipeline']['stages']:
        if stage['name'] == 'Source':
            for action in stage['actions']:
                if action['name'] == 'Configuration':
                    bucket = action['configuration'].get('S3Bucket')
                    object_key = action['configuration'].get('S3ObjectKey')
                    LOGGER.info("Bucket: %s ObjectKey: %s", bucket, object_key)

    return bucket, object_key


@dataclass
class HelperCodePipeline:
    """Helper class for working with AWS CodePipeline
    
    Attributes:
        pipeline_name (str): Name of the CodePipeline
        cp_client (boto3.client): Boto3 CodePipeline client
        
    Helper methods for common CodePipeline operations.
    """
    pipeline_name: str
    cp_client: boto3.client = boto3.client("codepipeline")

    def get(self):
        """Get information about the pipeline"""
        return self.cp_client.get_pipeline(name=self.pipeline_name)

    def status(self, execution_id: str, max_attempts: int = 5) -> str:
        """Get the status of a pipeline execution

        Args:
            execution_id (str): The CodePipeline execution ID for a released run
            max_attempts (int): The maximum number of attempts to check the status of the execution before raising an exception. Defaults to 5.

        Returns:
            str: The status of the execution 'Cancelled'|'InProgress'|'Stopped'|'Stopping'|'Succeeded'|'Superseded'|'Failed'
        """
        _attempts = 0
        while True:
            try:
                _execution = self.cp_client.get_pipeline_execution(
                    pipelineName=self.pipeline_name, pipelineExecutionId=execution_id
                )
                return _execution["pipelineExecution"]["status"]

            except (
                self.cp_client.exceptions.PipelineExecutionNotFoundException
            ) as not_started_exception:
                if _attempts >= max_attempts:
                    raise not_started_exception
                LOGGER.info("Status lookup not found...waiting 5s and will retry")
                _attempts += 1
                sleep(check_delay())

    def other_running_executions(self) -> list:
        """Check if there are other executions of the pipeline
        currently running"""
        _paginator = self.cp_client.get_paginator("list_pipeline_executions")
        _iterator = _paginator.paginate(pipelineName=self.pipeline_name)
        _running_executions = list(
            _iterator.search("pipelineExecutionSummaries[?status == `InProgress`]")
        )
        LOGGER.info(
            "Existing running executions lookup returned: %s", _running_executions
        )
        return _running_executions

    def start_execution(self) -> str:
        """Start the CodePipeline release execution

        Returns:
            str: The CodePipeline Execution ID
        """
        return self.cp_client.start_pipeline_execution(name=self.pipeline_name)[
            "pipelineExecutionId"
        ]
