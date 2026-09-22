from aigateway.auth.app import create_app
from aigateway.config import AuthSettings
from aigateway.telemetry import setup_logging

settings = AuthSettings()
setup_logging(settings.service_name, settings.log_level)
app = create_app(settings)
