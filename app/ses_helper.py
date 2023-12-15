# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

from aws_cdk import (
    aws_ses as ses
)


def create_ses_identity(scope, identity_name: str, identity_email: str) -> ses.IEmailIdentity:
    i_ses_identify = ses.EmailIdentity(scope, f"rSesIdentity{identity_name.title().replace('_','')}",
        identity=ses.Identity.email(email=identity_email)
    )
    return i_ses_identify
