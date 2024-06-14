# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import logging
import yaml

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


def get_services_to_validate():
    """
    Loads validation configuration from YAML file.

    Returns a list of booleans specifying which AWS services 
    should be validated based on the contents of the YAML file.
    """
    with open('./validate.yaml', 'rb') as file:
        return yaml.safe_load(file)
