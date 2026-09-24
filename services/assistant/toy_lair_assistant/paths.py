from pathlib import Path


def resolve_creation_dir(here: Path) -> Path:
    if len(here.parents) > 3:
        repo_creation = here.parents[3] / "rabbit" / "assistant"
        if (repo_creation / "index.html").exists():
            return repo_creation
    return here.parents[1] / "static" / "creation"


def creation_dir() -> Path:
    return resolve_creation_dir(Path(__file__).resolve())


def resolve_paco_dir(here: Path) -> Path:
    if len(here.parents) > 3:
        repo_paco = here.parents[3] / "rabbit" / "paco"
        if (repo_paco / "index.html").exists():
            return repo_paco
    return here.parents[1] / "static" / "paco"


def paco_dir() -> Path:
    return resolve_paco_dir(Path(__file__).resolve())


def resolve_carlos_dir(here: Path) -> Path:
    if len(here.parents) > 3:
        repo_carlos = here.parents[3] / "rabbit" / "carlos"
        if (repo_carlos / "index.html").exists():
            return repo_carlos
    return here.parents[1] / "static" / "carlos"


def carlos_dir() -> Path:
    return resolve_carlos_dir(Path(__file__).resolve())
