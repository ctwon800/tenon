FROM python:3.10-bullseye
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN python3 -m pip install -i https://mirrors.aliyun.com/pypi/simple -r requirements.txt
COPY . .
CMD ["uvicorn", "src.api:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]