from pathlib import Path


def resolve_creation_dir(here: Path) -> Path:
    if len(here.parents) > 3:
        repo_creation = here.parents[3] / "rabbit" / "assistant"
        if (repo_creation / "index.html").exists():
            return repo_creation
    return here.parents[1] / "static" / "creation"


def creation_dir() -> Path:
    return resolve_creation_dir(Path(__file__).resolve())
