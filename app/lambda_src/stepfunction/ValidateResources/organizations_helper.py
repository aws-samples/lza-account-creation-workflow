# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import logging
import boto3

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


ORGS_CLIENT = boto3.client('organizations')


def get_ou_ids(ou_path: str):
    """
    Get Organizational Unit ID for the Suspended OU Path and Root ID
    
    Args:
        ou_path (str): Suspended Organizational Unit Path. The path will use : as a path seperator.
    
    Returns:
        dict: AWS Organizations Root ID, ID of Suspended Organizational Unit
    """
    LOGGER.info(f"Getting AWS Organizations Id for OU Path: {ou_path}")
    root_id = ORGS_CLIENT.list_roots()['Roots'][0]['Id']
    path = ou_path.split('/')

    _id = root_id
    while path:
        path_exist = False
        list_organizational_units_for_parent = ORGS_CLIENT.get_paginator('list_organizational_units_for_parent')
        for _org_ids in list_organizational_units_for_parent.paginate(ParentId=_id):
            for __orgs_id in _org_ids['OrganizationalUnits']:
                if __orgs_id['Name'] == path[0]:
                    LOGGER.info(f"Found Name:{__orgs_id['Name']} Id:{__orgs_id['Id']}")
                    _id = __orgs_id['Id']
                    path.pop(0)
                    path_exist = True
                    break

            if not path_exist:
                raise Exception(f"Did not find OU Path ({ou_path}) in OU Structure")

    return _id


def is_account_exist_in_ou(account_id: str, ou_name: str):
    """
    Validates account exists in organizational unit.

    Checks if the given account ID exists as a child of the 
    organizational unit by name. Returns result of validation check.

    Args:
        account_id (str): ID of account to validate
        ou_name (str): Name of organizational unit 

    Returns: 
        dict: Validation result
    """
    LOGGER.info(f"Validating that Account: {account_id} exists in OU: {ou_name}")
    ou_id = get_ou_ids(ou_path=ou_name)

    _paginator = ORGS_CLIENT.get_paginator('list_children')
    _iterator = _paginator.paginate(ParentId=ou_id, ChildType='ACCOUNT')
    acc_list = list(_iterator.search(f"Children[?Id=='{account_id}']"))
    if not acc_list:
        status = "Failed"
        validation_msg = "Account does NOT exist with the requested Organizational Unit"
    else:
        status = "Passed"
        validation_msg = "Validated that the Account exists with the requested Organizational Unit"

    return {
        "Service": "OrganizationalUnitValidation",
        "Status": status,
        "Message": validation_msg
    }
