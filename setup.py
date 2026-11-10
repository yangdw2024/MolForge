from setuptools import setup, find_packages

setup(
    name="molforge-studio",
    version="7.4.0",
    packages=find_packages(include=["molforge", "molforge.*"]),
    py_modules=["main"],
    include_package_data=True,
)
