ARG BUILD_FROM
FROM ${BUILD_FROM}

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install Python and dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-requests \
    py3-cryptography \
    py3-openssl \
    libffi-dev \
    openssl-dev \
    gcc \
    musl-dev \
    python3-dev

# Install Python packages
COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Create working directory
WORKDIR /app

# Copy Python files
COPY run.py /app/
COPY onecom_api.py /app/
COPY acme_manager.py /app/
COPY certificate_manager.py /app/

# Create SSL directory
RUN mkdir -p /ssl /data/acme /data/ssl

# Make run.py executable
RUN chmod +x /app/run.py

# Set Python path
ENV PYTHONPATH=/app

# Run the application
CMD ["python3", "/app/run.py"]
