FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY . .

# The bridge refuses a non-loopback bind without a token, so a missing
# HOTSEAT_TOKEN fails the boot loudly instead of serving an open instance.
EXPOSE 8765
CMD ["sh", "-c", "python -m hotseat_core --serve --host 0.0.0.0 --port ${PORT:-8765} --token ${HOTSEAT_TOKEN:?set HOTSEAT_TOKEN before starting}"]
