import threading
from urllib.parse import quote

from flask import current_app, render_template
from flask_mail import Message

from app import mail


def run_in_background(fn, *args):
    """Run fn(*args) in an app context off the request thread, so response
    time doesn't depend on whether (or how slowly) an email is sent.
    Synchronous under test, so tests stay deterministic."""
    app = current_app._get_current_object()

    def target():
        with app.app_context():
            try:
                fn(*args)
            except Exception:
                app.logger.exception("background task %s failed", fn.__name__)

    if app.testing:
        target()
    else:
        threading.Thread(target=target, daemon=True).start()


def send_email(subject, sender, recipients, text_body, html_body):
    msg = Message(
        subject, sender=("The Invoicer", sender), recipients=recipients
    )
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
        text_body=render_template(
            "email/reset_password.txt", user=user, token=token
        ),
        html_body=render_template(
            "email/reset_password.html", user=user, token=token
        ),
    )


def _send_password_reset_email_by_id(user_id):
    from app.models.user import User

    user = User.query.filter_by(id=user_id).first()
    if user:
        send_password_reset_email(user)


def queue_password_reset_email(user):
    run_in_background(_send_password_reset_email_by_id, user.id)


def send_confirm_mail(user_email, token):
    confirm_url = (
        f"{current_app.config['SITE_DOMAIN']}/confirm-email/{quote(token)}"
    )
    send_email(
        "Please confirm your email",
        sender=current_app.config["MAIL_DEFAULT_SENDER"],
        recipients=[user_email],
        text_body="Text body",
        html_body=render_template(
            "email/email_confirm.html", confirm_url=confirm_url
        ),
    )
