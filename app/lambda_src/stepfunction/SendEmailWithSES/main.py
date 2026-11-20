# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
import logging
import json
from dataclasses import dataclass
from typing import Tuple, Optional

import boto3
from botocore.exceptions import ClientError

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOGGER = logging.getLogger()
LOGGER.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logging.getLogger("botocore").setLevel(logging.ERROR)


@dataclass
class EmailData:
    """Structure of email template input"""
    subject: str
    email_heading: str
    opening_paragraph: str
    account_name: str
    account_id: str
    sso_url: str
    to_addresses: str
    cc_list: Optional[str] = None
    bcc_list: Optional[str] = None

    def __post_init__(self):
        self.to_addresses = self.to_addresses.replace(' ', '').split(',')

        if self.cc_list and self.cc_list != 'None':
            self.cc_list = self.cc_list.replace(' ', '').split(',')
        else:
            self.cc_list = []

        if self.bcc_list and self.bcc_list != 'None':
            self.bcc_list = self.bcc_list.replace(' ', '').split(',')
        else:
            self.bcc_list = []

    def generate_email_html(self) -> Tuple[str, str]:
        """Generate HTML and plain text content for an email.

        Returns:
            Tuple[str, str]: A tuple containing the HTML string and plain text string.
        """
        html = f"""
<!DOCTYPE  html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional/EN" \
"http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
    <title>Account Created Email</title>
    <meta name="viewport? content="width=device-width, initial-scale=1.0">
</head>
<body>
    <h1>{self.email_heading}</h1>
    <p>{self.opening_paragraph}</p>
    <table>
        <tr>
            <td><strong>Account Name: </strong></td><td>{self.account_name}</td>
        </tr>
        <tr>
            <td><strong>Account ID: </strong></td><td>{self.account_id}</td>
        </tr>
        <tr>
            <td><strong>SSO Login URL: </strong></td><td>{self.sso_url}</td>
        </tr>
    </table>
</body>
</html>
"""
        text = (
            "%s\n\n%s\n\n"
            "Account ID: %s\nAccount Name: %s\nSSO Login URL: %s"
            % (self.email_heading, self.opening_paragraph,
               self.account_id, self.account_name, self.sso_url)
        )

        return html, text

    def send_email(self) -> dict:
        """Send email message using SES."""
        email_html, email_text = self.generate_email_html()
        LOGGER.debug('Email html: %s', email_html)
        LOGGER.debug('Email text: %s', email_text)

        LOGGER.info('Attempting to send email using info in payload...')
        ses_client = boto3.client('ses')
        result = ses_client.send_email(
            Source=os.getenv('FROM_EMAIL_ADDRESS'),
            Destination={
                'ToAddresses': self.to_addresses,
                'CcAddresses': self.cc_list,
                'BccAddresses': self.bcc_list
            },
            Message={
                'Subject': {'Data': self.subject},
                'Body': {
                    'Text': {'Data': email_text},
                    'Html': {'Data': email_html}
                }
            },
            SourceArn=os.getenv('SES_IDENTITY_ARN')
        )
        LOGGER.info('Email successfully sent')
        LOGGER.debug('SES response: %s', result)
        return result


def lambda_handler(event, context):
    """Send account creation notification emails via SES.

    Args:
        event (dict): The event dict containing the trigger information and payload.
        context (object): Lambda context runtime methods and attributes.

    Returns:
        dict: Updated payload including the email sending status.
    """
    LOGGER.debug('Event: %s', json.dumps(event))
    try:
        payload = event['Payload']
        payload['EmailSentToOwner'] = False

        email_data = EmailData(**payload['EmailInfo'])
        email_data.send_email()
        payload['EmailSentToOwner'] = True
        return payload

    except ClientError as client_err:
        LOGGER.error(
            "SES API error sending email: %s", client_err.response['Error']['Message']
        )
        raise RuntimeError(str(client_err)) from client_err
    except (KeyError, TypeError) as data_err:
        LOGGER.error("Invalid email data in payload: %s", data_err)
        raise RuntimeError(str(data_err)) from data_err
    except Exception as e:
        LOGGER.exception("Unexpected error in SendEmailWithSES")
        raise RuntimeError(str(e)) from e
