FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Apply latest Debian security patches to reduce base-image CVEs.
RUN apt-get update \
  && apt-get upgrade -y \
  && apt-get autoremove -y \
  && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source.
COPY . .

# Non-root runtime user.
ARG APP_USER=careerpilot
RUN useradd -m -s /bin/bash "${APP_USER}" \
  && chown -R "${APP_USER}":"${APP_USER}" /app
USER ${APP_USER}

CMD ["sh", "-c", "python -m uvicorn api:app --host 0.0.0.0 --port ${PORT:-8080}"]
