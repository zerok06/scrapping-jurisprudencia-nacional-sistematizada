# Usar la imagen oficial de Playwright con Python preinstalado
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Evitar prompts interactivos de apt
ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_ROOT_USER_ACTION=ignore

# Instalar dependencias del sistema requeridas por OpenCV (usado en PaddleOCR/OCR fallback)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Establecer directorio de trabajo
WORKDIR /app

# Copiar requirements.txt primero para aprovechar la caché de Docker
COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Los navegadores (Chromium) ya vienen preinstalados en la imagen base de Playwright.
# Omitimos la descarga externa de Chrome estable para evitar bloqueos y acelerar el build.

# Copiar el resto del código del proyecto
COPY . .

# Exponer el puerto por defecto de Streamlit
EXPOSE 8501

# Comando por defecto para correr la app de Streamlit
CMD ["streamlit", "run", "src/dashboard.py", "--server.port=8501", "--server.address=0.0.0.0"]
