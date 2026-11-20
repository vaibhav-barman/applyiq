"""The app instance uvicorn serves (`uvicorn app.main:app`). Tests use `app.factory`."""

from app.factory import create_app

app = create_app()
