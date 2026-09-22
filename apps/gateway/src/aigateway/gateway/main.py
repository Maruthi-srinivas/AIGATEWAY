from aigateway.config import GatewaySettings
from aigateway.gateway.app import create_app
from aigateway.telemetry import setup_logging

settings = GatewaySettings()
setup_logging(settings.service_name, settings.log_level)
app = create_app(settings)
