import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from googleapiclient.discovery import build
from google.auth import default


def fetch_service_account_data():
    credentials, project_id = default()
    service = build("iam", "v1", credentials=credentials)

    # Get service accounts
    accounts = service.projects().serviceAccounts().list(
        name=f"projects/{project_id}"
    ).execute()

    report = f"🚀 GCP Service Account Key Report\n📅 Timestamp: {datetime.now(timezone.utc)}\n"
    report += "-" * 40 + "\n"

    for sa in accounts.get("accounts", []):
        email = sa["email"]
        name = sa["name"]

        keys = service.projects().serviceAccounts().keys().list(name=name).execute()
        if "keys" not in keys:
            report += f"🔹 {email} — No keys found\n"
            continue

        for key in keys["keys"]:
            key_id = key.get("name", "").split("/")[-1]
            created = key.get("validAfterTime")
            expiry = key.get("validBeforeTime")
            expired = False

            if expiry:
                expiry_time = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                remaining = (expiry_time - datetime.now(timezone.utc)).days
                if remaining < 0:
                    expired = True

                color = "🟥" if remaining <= 10 else "🟩"
                report += f"{color} {email} | Key: {key_id} | Expires in: {remaining} days\n"
            else:
                report += f"🟨 {email} | Key: {key_id} | No expiry set\n"

    return report


def notify_email(event, context):
    try:
        # Compose email message
        report = fetch_service_account_data()

        username = os.environ["username"]
        password = os.environ["password"]
        sender = os.environ["sender"]
        smtp_server = os.environ.get("SMTP", "smtp.gmail.com")
        recipients = os.environ["recipients"].split(",")

        email = EmailMessage()
        email.set_content(report)
        email["Subject"] = "🚨 GCP Service Account Key Expiry Audit"
        email["From"] = sender
        email["To"] = recipients

        with smtplib.SMTP_SSL(smtp_server, 465) as smtp:
            smtp.login(username, password)
            smtp.send_message(email)

        print("✅ Email sent successfully.")

    except Exception as e:
        print(f"❌ Error in notify_email: {e}")
