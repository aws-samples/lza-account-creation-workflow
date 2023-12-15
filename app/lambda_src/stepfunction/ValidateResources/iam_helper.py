# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import logging
import boto3

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


class ValidateIam:
    """Class to validate IAM
    """
    creds = {}

    def __init__(self, assumed_creds: dict):
        self.creds = assumed_creds
        iam_args = {"service_name": "iam"}
        iam_args.update(self.creds)
        self.iam_client = boto3.client(**iam_args)

    def iam_role_exist(self, role_name: str):
        LOGGER.info(f"Checking if IAM Role ({role_name}) exists.")
        _paginator = self.iam_client.get_paginator('list_roles')
        _iterator = _paginator.paginate()
        _roles = list(_iterator.search(f"Roles[?RoleName=='{role_name}']"))

        if not _roles:
            status = "Failed"
            validation_msg = f"IAM Role {role_name} does NOT exist in the newly created Account"
        else:
            status = "Passed"
            validation_msg = f"IAM Role {role_name} exists"

        return {
            "Service": f"IAMRoleValidation_{role_name}",
            "Status": status,
            "Message": validation_msg
        }
