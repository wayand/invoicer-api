from flask_mail import Message
from flask import current_app
from app import mail
from flask import render_template


def send_email(subject, sender, recipients, text_body, html_body):
    msg = Message(subject, sender=("The Invoicer", sender), recipients=recipients)
    msg.body = text_body
    msg.html = html_body
    mail.send(msg)


def send_totp_code_email(user):
    html_title = "Two-factor Code"
    totp_code = user.get_totp_code(expire_in_sec=3600)
    user_name = user.name
    send_email(
        "Your OTP code",
        sender=current_app.config["MAIL_DEFAULT_SENDER"],
        recipients=[user.email],
        text_body=render_template(
            "email/totp_code.txt",
            user_name=user_name,
            totp_code=totp_code,
        ),
        html_body=render_template(
            "email/totp_code.html",
            html_title=html_title,
            user_name=user_name,
            totp_code=totp_code,
        ),
    )


def send_password_reset_email(user):
    token = user.get_reset_password_token()
    send_email(
        "[Invoicer App] Reset Your Password",
        sender=current_app.config["MAIL_DEFAULT_SENDER"],
        recipients=[user.email],
        text_body=render_template("email/reset_password.txt", user=user, token=token),
        html_body=render_template("email/reset_password.html", user=user, token=token),
    )


def send_confirm_mail(user_email, token):
    confirm_url = f"{current_app.config['SITE_DOMAIN']}/confirm-email/{token}"
    send_email(
        "Please confirm your email",
        sender=current_app.config["MAIL_DEFAULT_SENDER"],
        recipients=[user_email],
        text_body="Text body",
        html_body=render_template("email/email_confirm.html", confirm_url=confirm_url),
    )
