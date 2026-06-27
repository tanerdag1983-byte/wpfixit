import pytest
from fastapi import FastAPI

from app.api.routes.page_packages import router as page_packages_router
from app.core.security import CurrentUser, get_current_user
from app.domains.audits import models as audit_models  # noqa: F401
from app.domains.projects.models import Profile
from app.domains.recommendations import models as recommendation_models  # noqa: F401
from tests.recommendations.conftest import *  # noqa: F403


@pytest.fixture
def auth_as():
    app = FastAPI()
    app.include_router(page_packages_router)

    def authenticate(profile: Profile) -> None:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id=profile.id,
            email=profile.email,
        )

    authenticate.app = app
    yield authenticate
    app.dependency_overrides.clear()
