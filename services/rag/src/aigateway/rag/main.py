from aigateway.config import RagSettings
from aigateway.rag.app import create_app

settings = RagSettings()
app = create_app(settings)
