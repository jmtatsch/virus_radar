FROM python:3.11-slim

WORKDIR /app

#Install Cron
RUN apt-get update && apt-get -y install cron git nano

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code & data
COPY app.py app.py
COPY geocode.py geocode.py
COPY location_manager.py location_manager.py
COPY .streamlit/ .streamlit/
COPY data/ data/

COPY .git /app/.git
COPY .gitmodules /app/.gitmodules

# Add the script to the Docker Image
ADD update.sh /app/update.sh

# Give execution rights on the cron scripts
RUN chmod 0644 /app/update.sh

# Add the cron job for hourly update
RUN crontab -l | { cat; echo "@hourly bash /app/update.sh"; } | crontab -

# Expose port 8501, default for Streamlit, and run the app
EXPOSE 8501
CMD ["streamlit", "run", "app.py"]