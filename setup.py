from setuptools import setup, find_packages

setup(
    name="photo-magazine",
    version="1.0.0",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "click>=8.0",
        "python-dotenv",
        "Pillow>=10.0",
        "pillow-heif",
        "flask>=3.0",
        "werkzeug",
        "Jinja2>=3.0",
        "google-auth",
        "google-auth-oauthlib",
        "requests",
        "tqdm",
        "pypdf",
    ],
    extras_require={
        "local": [
            "deepface",
            "tf-keras",
            "weasyprint>=62",
        ],
    },
    entry_points={
        "console_scripts": [
            "magazine=magazine.cli:cli",
        ],
    },
)
