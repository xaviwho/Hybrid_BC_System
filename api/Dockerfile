FROM python:3.9-slim

WORKDIR /app

# Install required packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV HYPERLEDGER_URL=http://hybrid-peer0.org1.example.com:8051
ENV ETHEREUM_URL=http://ethereum-node:8545
ENV ML_GATEWAY_URL=http://ml-gateway-filter:5000
ENV ML_PRIVACY_URL=http://ml-privacy-filter:5001

# Expose port
EXPOSE 8000

# Run the system orchestrator
CMD ["python", "system_orchestrator.py"]
