"""Include readable module resources in wheels as well as source archives."""
from pathlib import Path
from shutil import copy2

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithResources(build_py):
    def run(self):
        super().run()
        root = Path(__file__).parent
        target = Path(self.build_lib) / "legends_hetzner" / "_data"
        for folder in ("docs", "knowledge", "cloud-init", "skills"):
            source = root / folder
            if source.is_dir():
                for path in sorted(source.rglob("*")):
                    if path.is_file() and path.suffix in (".md", ".json", ".yaml"):
                        dest = target / path.relative_to(root)
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        copy2(path, dest)
        for name in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
            copy2(root / name, target / name)


setup(cmdclass={"build_py": BuildWithResources})
