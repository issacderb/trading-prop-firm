FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã nguồn bao gồm main.py, crypto_engine.py, vn_stock_sniper.py, và các file cấu hình
COPY . .

CMD ["python", "-u", "main.py"]
