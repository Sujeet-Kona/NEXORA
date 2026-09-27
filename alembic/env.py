from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.core.config import settings
from backend.db.models import Base


config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False keeps the application's "nexora" logger
    # (imported before migrations run) alive. The default of True would mark it
    # disabled, silently dropping all app/audit/observability logs emitted after
    # an in-process migration.
    fileConfig(
        config.config_file_name,
        disable_existing_loggers=False,
    )


database_url = config.get_main_option("sqlalchemy.url")

if not database_url or database_url.startswith("driver://"):
    database_url = settings.database_url


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        {
            **config.get_section(config.config_ini_section, {}),
            "sqlalchemy.url": database_url,
        },
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()