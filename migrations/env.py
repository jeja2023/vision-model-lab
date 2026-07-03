from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    url = os.environ.get("VMLAB_METADATA_DB", "sqlite:///artifacts/vision_model_lab.sqlite3")
    context.configure(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine

    url = os.environ.get("VMLAB_METADATA_DB", "sqlite:///artifacts/vision_model_lab.sqlite3")
    connectable = create_engine(url)
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
