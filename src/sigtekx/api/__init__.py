"""HTTP API for orchestrating SigTekX cloud benchmark runs.

This subpackage is intentionally NOT imported from ``sigtekx/__init__.py``.
It depends on FastAPI, uvicorn and boto3, which are optional extras
(``pip install sigtekx[api]``). Importing it eagerly would break a plain
``import sigtekx`` for users who never asked for the API.

Import the app explicitly instead::

    from sigtekx.api.app import app
"""
