import subprocess
import sys


def test_page_package_models_register_blueprint_table() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.core.database import Base; "
                "import app.domains.page_packages.models; "
                "assert 'page_blueprints' in Base.metadata.tables"
            ),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
