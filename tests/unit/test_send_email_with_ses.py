# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import pytest
from moto import mock_ses
from moto.core import DEFAULT_ACCOUNT_ID
from moto.ses import ses_backends

from app.lambda_src.stepfunction.SendEmailWithSES.main import EmailData


TEST_EMAIL_DATA = {
    "subject": "test subject",
    "email_heading": "This is a heading",
    "opening_paragraph": "Some text below the heading",
    "account_name": "Test Account",
    "account_id": "01234567890",
    "sso_url": "https://www.example.com",
    "to_addresses": "test@test.com",
    "cc_list": "blah@blah.com,foo@foo.com",
    "bcc_list": "bar@bar.com",
}


def test_generate_email_html(aws_credentials):
    """Test function for generate email html method"""
    with mock_ses():
        test_email = EmailData(**TEST_EMAIL_DATA)
        html, text = test_email.generate_email_html()
        assert "<html" in html
        assert "<html" not in text
        assert TEST_EMAIL_DATA["opening_paragraph"] in html
        assert TEST_EMAIL_DATA["opening_paragraph"] in text


def test_send_email(aws_credentials, mocked_ses_backend):
    """Test function for the send email method"""
    ses_backend = mocked_ses_backend
    test_email = EmailData(**TEST_EMAIL_DATA)
    response = test_email.send_email()
    assert response.get("MessageId")
    sent_messages = list(ses_backend.sent_messages)
    assert len(sent_messages) == 1
    sent_message = sent_messages[0]
    assert sent_message.id == response.get("MessageId")
    assert sent_message.destinations["ToAddresses"] == [TEST_EMAIL_DATA["to_addresses"]]
    html, _ = test_email.generate_email_html()
    assert sent_message.body == html


def test_no_bcc_or_cc(aws_credentials, mocked_ses_backend):
    """Test function from empty bcc and cc lists for sending properly still"""
    ses_backend = mocked_ses_backend
    no_cc_data = TEST_EMAIL_DATA.copy()
    del no_cc_data["cc_list"]
    del no_cc_data["bcc_list"]
    test_email = EmailData(**no_cc_data)
    assert test_email.cc_list == []
    assert test_email.bcc_list == []
    no_cc_data["cc_list"] = "None"
    no_cc_data["bcc_list"] = "None"
    assert test_email.cc_list == []
    assert test_email.bcc_list == []
    response = test_email.send_email()
    messages = list(ses_backend.sent_messages)
    assert len(messages) == 1
    assert messages[0].id == response.get("MessageId")
