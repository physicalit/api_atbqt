# Use a Python base image
FROM python:3.11-slim

# Create the www-data user and group if they don't exist
# RUN groupadd -r www-data && useradd -r -g www-data www-data

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*


# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Flask application code into the container
COPY . /app

# Change the ownership of the /app directory to www-data
RUN chown -R www-data:www-data /app

# Change the user to www-data
USER www-data

# Expose the port on which your application will run
EXPOSE 8080

# Start uWSGI
CMD ["uwsgi", "--ini", "uwsgi.ini"]
