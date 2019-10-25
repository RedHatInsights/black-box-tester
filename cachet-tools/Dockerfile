# Get centos base image
# Use FROM scratch for blank image
FROM python:2

# who are you
MAINTAINER bennyturns

COPY requirements.txt /

# Run when creating image
RUN pip install --no-cache-dir -r /requirements.txt

# copy file into place
COPY cachet_update_daemon.py / 

# Expose the port
EXPOSE 10000

# Executed once image is up / container is created
#CMD ["ls -l"]
CMD ["python", "/cachet_update_daemon.py"]
