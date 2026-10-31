import glob
import json

import click
from flask.cli import with_appcontext
from sqlalchemy import exc

from app.chart import apply_starter_chart
from app.models.account import Account
from app.models.base import db
from app.models.contact import Contact
from app.models.country import Country
from app.models.invoice import Invoice
from app.models.invoiceline import InvoiceLine
from app.models.organization import Organization
from app.models.product import Product
from app.models.user import User
from app.models.vat_code import VatCode


@click.command()
@with_appcontext
def seed():
    """Seed the user database."""

    # create new category
    default_country = Country.query.filter_by(id=1).first()
    if not default_country:
        new_country = Country(
            currency_id="DKK", locale_id="da_DK", name="Danmark", icon="dk"
        )
        new_country.save()
        click.echo("created country")
    else:
        click.echo(f"country already exists: {default_country.name}")

    # organizations
    organizations = glob.glob("app/seed/orgs/*.json", recursive=False)
    for org_json_path in organizations:
        with open(org_json_path, "r") as f:
            org_data = json.load(f)
            click.echo("\nCreating Organization: " + org_data.get("name"))

            # extracting users, contacts and products
            org_users = org_data.pop("users")
            org_products = org_data.pop("products")
            org_contacts = org_data.pop("contacts")
            bank_account = org_data.pop("bank_account", None)

            organization_obj = Organization.find_by(
                name=org_data.get("name"),
                slug=org_data.get("slug"),
                email=org_data.get("email"),
            )

            if not organization_obj:
                organization_obj = Organization(**org_data)
                organization_obj.save()
                click.echo("done: " + org_data.get("name"))
            else:
                click.echo(
                    "already exists Organization: " + org_data.get("name")
                )

            ###########################
            # Organization -> users
            click.echo(
                "\n-> creating users for Organization: " + org_data.get("name")
            )
            if org_users:
                for user_data in org_users:
                    try:
                        user_data["organization_id"] = organization_obj.id
                        user_data["otp_secret"] = User.generate_otp_secret()
                        user_obj = User(**user_data)
                        user_obj.save()
                        click.echo("-- created user: " + user_data.get("name"))
                    except exc.IntegrityError as e:
                        db.session.rollback()
                        click.echo(
                            "-- already exists user: "
                            + user_data.get("name")
                            + str(e.args)
                        )
            else:
                click.echo("-- No users found")

            #############################
            # Organization -> Products
            click.echo(
                "\n-> creating products for Organization: "
                + org_data.get("name")
            )
            if org_products:
                for product_data in org_products:
                    product_obj = Product.find_by(
                        name=product_data.get("name"),
                        organization_id=organization_obj.id,
                    )
                    if not product_obj:
                        product_data["organization_id"] = organization_obj.id
                        product_obj = Product(**product_data)
                        product_obj.save()
                        click.echo(
                            "-- created product: " + product_data.get("name")
                        )
                    else:
                        click.echo(
                            "-- already exists: " + product_data.get("name")
                        )
            else:
                click.echo("-- No products found")

            ############################
            # Organization -> Contacts
            click.echo(
                "\n-> creating contacts for Organization: "
                + org_data.get("name")
            )
            if org_contacts:
                for contact_data in org_contacts:
                    # extract contact invoices
                    contact_invoices = contact_data.pop("invoices")

                    contact_obj = Contact.find_by(
                        name=contact_data.get("name"),
                        email=contact_data.get("email"),
                        organization_id=organization_obj.id,
                    )
                    if not contact_obj:
                        contact_data["organization_id"] = organization_obj.id
                        contact_obj = Contact(**contact_data)
                        contact_obj.save()
                        click.echo(
                            "-- created contact: " + contact_data.get("name")
                        )
                    else:
                        click.echo(
                            "-- already exists: " + contact_data.get("name")
                        )

                    #####################
                    # contact invoices
                    click.echo(
                        "\n-- -> creating invoices for contact: "
                        + contact_data.get("name")
                    )

                    if contact_invoices:
                        for invoice_data in contact_invoices:
                            try:
                                invoice_data["organization_id"] = (
                                    organization_obj.id
                                )
                                invoice_data["contact_id"] = contact_obj.id
                                lines = invoice_data.pop("lines")

                                # add product and VAT code to invoiceLine
                                for line in lines:
                                    line["product_id"] = product_obj.id
                                    line["vat_code_id"] = (
                                        VatCode.query.filter_by(
                                            code=line.pop("vat_code")
                                        )
                                        .one()
                                        .id
                                    )

                                invoice_obj = Invoice(
                                    **invoice_data,
                                    lines=[
                                        InvoiceLine(**line) for line in lines
                                    ],
                                )
                                invoice_obj.save()
                                click.echo(
                                    "-- -- created invoice number: "
                                    + invoice_data.get("invoice_no")
                                )
                            except exc.IntegrityError:
                                db.session.rollback()
                                click.echo(
                                    "-- -- already exists: "
                                    + invoice_data.get("invoice_no")
                                )
            else:
                click.echo("-- No contacts found")

            #################################
            # Organization chart of accounts
            click.echo(
                "\n-> creating the chart of accounts for Organization: "
                + org_data.get("name")
            )
            result = apply_starter_chart(organization_obj)
            click.echo(_chart_summary(result))
            if bank_account:
                bank = Account.find_by(
                    organization_id=organization_obj.id, system_role="bank"
                )
                for key, value in bank_account.items():
                    setattr(bank, key, value)
                bank.save()
                click.echo("-- set the bank details on " + bank.name)


def _chart_summary(result):
    parts = [
        f"{len(result.created)} created",
        f"{len(result.adopted)} adopted",
        f"{len(result.unchanged)} already there",
    ]
    if result.skipped:
        parts.append(f"{len(result.skipped)} skipped")
    lines = ["-- accounts: " + ", ".join(parts)]
    for number, reason in sorted(result.skipped.items()):
        lines.append(f"-- skipped {number}: {reason}")
    return "\n".join(lines)


@click.command("chart-apply")
@click.argument("slug")
@with_appcontext
def chart_apply(slug):
    """Give the organization SLUG the starter chart of accounts of its
    company form. Safe to run again: accounts that exist are kept."""
    organization = Organization.find_by(slug=slug)
    if organization is None:
        raise click.ClickException(f"No organization with slug {slug}")
    result = apply_starter_chart(organization)
    click.echo(f"{organization.name} ({organization.company_form})")
    click.echo(_chart_summary(result))


@click.command("user-reset-2fa")
@click.argument("email")
@with_appcontext
def user_reset_2fa(email):
    """Recovery: put EMAIL back on email codes (drops the authenticator app
    and all backup codes). For when both the phone and the codes are lost."""
    user = User.find_by_email(email)
    if user is None:
        raise click.ClickException(f"No user with email {email}")
    user.reset_two_factor()
    click.echo(
        f"Two-factor reset for {email}: email codes, no backup codes, "
        "new secret."
    )


def register_commands(app):
    """Register CLI commands."""
    app.cli.add_command(seed)
    app.cli.add_command(chart_apply)
    app.cli.add_command(user_reset_2fa)
