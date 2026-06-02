"""Import hub that registers every personal-OS module's capability tools.

Importing this module registers the module CRUD tools (task.*, note.*, …) into the tool registry,
exactly as `import jarvis.connectors` registers connector act-Tools. Imported wherever the registry
must be populated before the conversation agent runs (gateway + CLI/daemon).
"""

from jarvis.documents import tools as _documents  # noqa: F401 — registers document.* tools
from jarvis.notes import tools as _notes  # noqa: F401 — registers note.* tools
from jarvis.recipes import tools as _recipes  # noqa: F401 — registers recipe.* tools
from jarvis.research import tools as _research  # noqa: F401 — registers research.run (gated)
from jarvis.tasks import tools as _tasks  # noqa: F401 — registers task.* tools
