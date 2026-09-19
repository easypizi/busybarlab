from pathlib import Path


def creation_dir() -> Path:
    here = Path(__file__).resolve()
    repo_creation = here.parents[3] / "rabbit" / "assistant"
    if (repo_creation / "index.html").exists():
        return repo_creation
    bundled = here.parents[1] / "static" / "creation"
    return bundled
