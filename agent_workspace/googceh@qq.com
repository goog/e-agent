import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email():
    # Email configuration
    sender_email = "your_email@gmail.com"
    receiver_email = "googceh@qq.com"
    password = "your_app_password"  # Use app password for Gmail

    # Create message
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = "Python Email Test"

    # Email body
    body = "This email was sent using Python."
    message.attach(MIMEText(body, "plain"))

    # Send email
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, password)
        server.sendmail(sender_email, receiver_email, message.as_string())
        server.quit()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    send_email()