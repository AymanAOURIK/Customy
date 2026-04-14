FROM python:3.13-slim

# Install pdflatex and required TeX packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-latex-recommended \
    texlive-font-utils \
    texlive-lang-french \
    lmodern \
    && rm -rf /var/lib/apt/lists/*

# Verify lmodern.sty is present — build fails here if the package is missing
RUN kpsewhich lmodern.sty

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV CUSTOMY_MODE=saas
ENV PYTHONUNBUFFERED=1
EXPOSE 8080

CMD ["python", "main.py", "--host", "0.0.0.0"]
