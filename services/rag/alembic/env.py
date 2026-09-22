import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from aigateway.rag.db import sqlalchemy_url
from aigateway.rag.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

dsn = os.environ["POSTGRES_DSN"]
config.set_main_option("sqlalchemy.url", sqlalchemy_url(dsn))
target_metadata = Base.metadata
VERSION_TABLE = "rag_alembic_version"


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        version_table=VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table=VERSION_TABLE,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
