# Use Python 3.8.10 slim image as base
FROM python:3.8-slim

# Install system dependencies for geospatial libraries
RUN apt-get update && apt-get install -y \
    libgeos-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements files first for better caching
COPY poaff_bpa/requirements.txt /tmp/poaff_req.txt
COPY aixmParser/requirements.txt /tmp/aixm_req.txt
COPY openairParser/requirements.txt /tmp/openair_req.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /tmp/poaff_req.txt && \
    pip install --no-cache-dir -r /tmp/aixm_req.txt && \
    pip install --no-cache-dir -r /tmp/openair_req.txt

# Copy the application code
COPY poaff_bpa/ poaff_bpa/
COPY aixmParser/ aixmParser/
COPY openairParser/ openairParser/
COPY docker-entrypoint.py /app/

# Create a volume for the output folder
VOLUME ["/app/poaff_bpa/output"]

# Set working directory to poaff_bpa/src for relative path compatibility
WORKDIR /app/poaff_bpa/src

# Set the entrypoint script
CMD ["python", "/app/docker-entrypoint.py"]