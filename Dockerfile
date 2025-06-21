FROM ubuntu:24.04
MAINTAINER Aleksey Karpov <admin@bitaps.com>
RUN apt update
RUN apt install python3-pip -y
RUN apt install git -y
COPY requirements.txt .
RUN python3 -m pip config set global.break-system-packages true
RUN pip3 install --requirement requirements.txt
RUN mkdir -p /config /app
COPY . /app/
WORKDIR /app
ENTRYPOINT ["python3", "main.py"]
