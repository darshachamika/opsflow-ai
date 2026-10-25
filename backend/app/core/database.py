from sqlalchemy import URL, create_engine

from app.core.config import settings


database_url = URL.create(
    drivername="postgresql+psycopg",
    username=settings.postgres_user,
    password=settings.postgres_password.get_secret_value(),
    host=settings.postgres_host,
    port=settings.postgres_port,
    database=settings.postgres_db,
    query={
        "sslmode": settings.postgres_sslmode,
        "channel_binding": settings.postgres_channel_binding,
    },
)

engine = create_engine(
    database_url,
    pool_pre_ping=True,
    connect_args={
        "connect_timeout": settings.postgres_connect_timeout,
    },
)