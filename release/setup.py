from setuptools import setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="make_release",
    version="1.0.0",
    author="Simeon Widdis",
    author_email="sawiddis@amazon.com",
    license="Apache-2.0",
    description="A script to automate OpenSearch release note writing",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Swiddis/opensearch-utils",
    py_modules=["make_release"],
    package_data={"": ["make_release.py"]},
    python_requires=">=3.10",
    install_requires=[
        "click==8.1.7",
        "requests==2.31.0",
    ],
    entry_points={
        "console_scripts": [
            "make_release=make_release:make_release",
        ],
    },
)
