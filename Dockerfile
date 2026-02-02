# Usamos una imagen oficial de Python con slim
FROM python:3.11-slim

# Actualizamos el sistema e instalamos dependencias que necesita Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Establecemos el directorio de trabajo
WORKDIR /app

# Copiamos los archivos de requisitos y los instalamos
COPY requirements.txt .
RUN pip install -r requirements.txt

# Instalamos los navegadores de Playwright
RUN playwright install --with-deps chromium

# Copiamos el resto del código
COPY . .

# Exponemos el puerto 8000 (FastAPI default)
EXPOSE 8000

# Comando para ejecutar la app
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
