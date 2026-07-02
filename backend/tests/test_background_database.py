from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import background_engine


def test_background_engine_unwraps_connection_bound_session() -> None:
    engine = create_engine("sqlite+pysqlite://")

    with engine.connect() as connection, Session(connection) as session:
        assert background_engine(session) is engine
