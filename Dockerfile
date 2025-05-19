FROM python:3.12-slim

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

# Add the entrypoint script
ADD docker-entrypoint.sh /app/docker-entrypoint.sh

# Give execution rights on the cron scripts
RUN chmod +x /app/update.sh

RUN chmod +x /app/docker-entrypoint.sh

# Add the cron job for hourly update
RUN crontab -l | { cat; echo "@hourly bash /app/update.sh"; } | crontab -
# Create a log file to be able to run tail
RUN touch /var/log/cron.log

# Expose port 8501, default for Streamlit, and run the app
EXPOSE 8501
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["streamlit", "run", "app.py"]