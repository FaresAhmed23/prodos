FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
# F-9: the app runs `alembic upgrade head` at startup (app.main.run_migrations),
# so the config and the revision scripts must be in the image too. Without these
# two lines the container fails on boot with "No 'script_location' key".
COPY alembic.ini .
COPY migrations ./migrations

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]