from setuptools import setup, find_packages
from pathlib import Path

long_description = Path("README.md").read_text(encoding="utf-8")

setup(
    name="scip-cli",
    version="1.0.0",
    description="Fast code intelligence via SCIP indexes",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Ariel Flesler",
    license="MIT",
    url="https://github.com/flesler/scip-cli",
    packages=find_packages(exclude=["tests*"]),
    package_data={
        "scip_cli": ["SKILL.md"],
    },
    entry_points={
        "console_scripts": [
            "scip-cli=scip_cli.__main__:main",
        ],
    },
    python_requires=">=3.7",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Code Generators",
    ],
)
