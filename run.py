import os

import config
from app import cli, create_app
from app.models.base import db
from app.models.invoice import Invoice
from app.models.invoiceline import InvoiceLine

#
# something
config_class = (
    config.DevelopmentConfig
    if os.environ.get("FLASK_ENV") == "development"
    else config.ProductionConfig
)
app = create_app(config_class)
cli.register_commands(app)


@app.shell_context_processor
def make_shell_context():
    return {"db": db, "Invoice": Invoice, "InvoiceLine": InvoiceLine}
