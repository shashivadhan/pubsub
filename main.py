from typing import List
from google.cloud import iam_admin_v1
from google.cloud.iam_admin_v1 import types
import csv
from googleapiclient.discovery import build
from oauth2client.client import GoogleCredentials
import datetime
import base64
import functions_framework
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# Triggered from a Pub/Sub message
@functions_framework.cloud_event
def send_notification(cloud_event):
    # Added print to debug event data
    print(f"Received event: {cloud_event}")

    # Original base64 decode print (you may keep or remove)
    print(base64.b64decode(cloud_event.data["message"]["data"]))
    print('START')

    credentials = GoogleCredentials.get_application_default()
    credentials = credentials.create_scoped(['https://www.googleapis.com/auth/cloud-platform'])
    service = build('cloudresourcemanager', 'v1', credentials=credentials)
    projects = service.projects().list().execute()

    iam_admin_client = iam_admin_v1.IAMClient()
    request = types.ListServiceAccountsRequest()
    results = []

    for i, project in enumerate(projects['projects']):
        project_id = project['projectId']
        request.name = f"projects/{project_id}"
        try:
            accounts = iam_admin_client.list_service_accounts(request=request)
            for account in accounts:
                keys = keyinfo(account.name, iam_admin_client)
                if keys:
                    results.extend(keys)
        except Exception as e:
            print(f"{request.name=}, {e=}")
        if i > 1000:
            break

    if results:
        sorted_list = sorted(results, key=lambda x: int(x[-1]))
        send_mail(sorted_list)
    print("done")

def send_mail(keys):
    print("start mail process")
    username = os.environ.get('username')
    password = os.environ.get('password')
    sender = os.environ.get('sender')
    SMTP = os.environ.get('SMTP')
    msg = MIMEMultipart('mixed')
    recipients = os.environ.get('recipients').split(',')

    content_html = "<html><body><h2>GCP Service Account Key Alert</h2><ul>"
    for key in keys:
        account, key_name, _, expires_at, days_left = key
        color = "red" if int(days_left) <= 10 else "black"
        content_html += f"<li><b>Account:</b> {account}<br><b>Key:</b> {key_name}<br><b>Expires at:</b> {expires_at}<br><b style='color:{color};'>Days left:</b> {days_left}</li><br>"
    content_html += "</ul></body></html>"

    msg['Subject'] = "GCP Service Account Key Alert"
    msg['From'] = sender
    msg["To"] = ', '.join(recipients)
    msg.attach(MIMEText("", 'plain'))
    msg.attach(MIMEText(content_html, 'html'))

    with smtplib.SMTP(SMTP, 2525) as mailServer:
        mailServer.starttls()
        mailServer.login(username, password)
        for recipient in recipients:
            mailServer.sendmail(sender, recipient, msg.as_string())

def keyinfo(account_name, iam_admin_client):
    keys = []
    request = types.ListServiceAccountKeysRequest()
    request.name = account_name
    request.key_types = [types.ServiceAccountKey.KeyType.USER_MANAGED]
    response = iam_admin_client.list_service_account_keys(request=request)

    for key in response.keys:
        valid_after_time = convert_nanoseconds_to_datetime(key.valid_after_time)
        valid_before_time = convert_nanoseconds_to_datetime(key.valid_before_time)
        key_type_name = key.key_type.name
        key_name = key.name.split("/")[-1]
        if key_type_name == "USER_MANAGED" and valid_before_time < datetime.datetime(2100, 11, 20, tzinfo=datetime.timezone.utc):
            today = datetime.datetime.now(tz=datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            gap = valid_before_time - today
            if gap.days > 0:
                keys.append([account_name, key_name, valid_after_time.strftime("%Y-%m-%d %H:%M:%S%z"), valid_before_time.strftime("%Y-%m-%d %H:%M:%S%z"), str(gap.days)])
    return keys

def convert_nanoseconds_to_datetime(dt_with_nanoseconds) -> datetime.datetime:
    return datetime.datetime(
        dt_with_nanoseconds.year,
        dt_with_nanoseconds.month,
        dt_with_nanoseconds.day,
        dt_with_nanoseconds.hour,
        dt_with_nanoseconds.minute,
        dt_with_nanoseconds.second,
        microsecond=dt_with_nanoseconds.nanosecond // 1000,
        tzinfo=dt_with_nanoseconds.tzinfo
    )
