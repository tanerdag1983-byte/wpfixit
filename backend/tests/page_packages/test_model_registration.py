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
                "blueprints = Base.metadata.tables['page_blueprints']; "
                "assert 'wordpress_snapshot_id' in blueprints.c; "
                "assert 'snapshot_version' in blueprints.c; "
                "assert 'schema_version' in blueprints.c"
            ),
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
