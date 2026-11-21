"""Model package for the 招商 AI persistence layer.

Importing this package registers both tables on ``Base.metadata``; Alembic
relies on that registration for autogenerate and ``alembic check``.
"""

from app.modules.sai.models.sai_output import SaiOutput
from app.modules.sai.models.sai_task import SaiTask

__all__ = ["SaiOutput", "SaiTask"]
