import os
from app import create_app, cli
from app.models import Invoice, InvoiceLine, db
import config

#
# something
config_class = config.DevelopmentConfig if os.environ.get('FLASK_ENV') == 'development' else config.ProductionConfig
app = create_app(config_class)
cli.register_commands(app)

@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'Invoice': Invoice, 'InvoiceLine': InvoiceLine}
