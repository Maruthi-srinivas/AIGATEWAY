from aigateway.config import GuardrailsSettings
from aigateway.guardrails.app import create_app

settings = GuardrailsSettings()
app = create_app(settings)
