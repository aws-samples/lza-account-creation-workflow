# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. 
# SPDX-License-Identifier: MIT-0

from aws_cdk import (
    aws_ses as ses
)


def create_ses_identity(scope, identity_name: str, identity_email: str) -> ses.IEmailIdentity:  
    """
    Creates an Amazon SES identity.

    Args:
        scope (Construct): The CDK construct scope in which to define this identity.
        identity_name (str): The name of the SES identity.
        identity_email (str): The email address for the SES identity.

    Returns:
        ses.IEmailIdentity: The created SES identity object.
    """
    i_ses_identify = ses.EmailIdentity(scope, f"rSesIdentity{identity_name.title().replace('_','')}",
        identity=ses.Identity.email(email=identity_email)
    )
    return i_ses_identify
