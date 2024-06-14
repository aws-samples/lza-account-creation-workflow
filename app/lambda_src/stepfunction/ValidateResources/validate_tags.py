# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import logging
import os
from dataclasses import dataclass
from typing import List
import boto3


LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


class AccountTagsValidationException(Exception):
    """Custom Exception"""


@dataclass
class ValidateAccountTags:
    """
    Validates the tags on an AWS account.

    The class assumes an IAM role to make API calls. It contains
    a method to check if the tags on an account match the expected tags.
    """
    account_id: str
    tags: List[dict]
    org_client: boto3.client = boto3.client('organizations')

    def _get_account_tags(self):
        """Get the tags on an account"""
        return self.org_client.list_tags_for_resource(
            ResourceId=self.account_id
        ).get("Tags", [])

    def validate(self):
        """Compare existing tags to expected tags"""
        response = {
            "Service": "AccountTagsValidation",
        }
        _existing_tags = self._get_account_tags()
        diff = [e_item for e_item in _existing_tags if e_item not in self.tags]
        diff.extend(
            [n_item for n_item in self.tags if n_item not in _existing_tags])

        # Since SCProvisionedProductId is added directly it is allowed to be in diff
        if len(diff) == 0 or (len(diff) == 1 and diff[0].get('Key') == 'SCProvisionedProductId'):
            response['Status'] = 'Succeeded'
            response['Message'] = f'Existing tags match expected tags for account {self.account_id}'
            return response

        raise AccountTagsValidationException(
            'The existing tags and expected tags do not match.\n'
            f'\tExisting tags: {_existing_tags}\n'
            f'\tExpected tags: {self.tags}\n'
            f'\tDifference: {diff}\n')
