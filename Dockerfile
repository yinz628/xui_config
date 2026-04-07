FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY generate_xray_config.py /app/generate_xray_config.py
COPY xui_port_pool_generator /app/xui_port_pool_generator

CMD ["python", "generate_xray_config.py", "--mapping", "/app/config/mapping.yaml", "--template", "/app/config/config.json"]
