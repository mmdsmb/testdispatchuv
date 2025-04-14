# Use Python 3.9 slim image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install uv
RUN pip install uv

# Copy requirements
COPY pyproject.toml .

# Install dependencies using uv
#RUN uv pip install -e .
#RUN uv pip install --system .
# Install dependencies using uv with --system
RUN uv pip install --system -e .

# Copy application code
COPY . .

# Expose port
EXPOSE 8080


# Command to run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"] 