FROM python:3.12-slim
WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV DATA_DIR=/data \
    DATA_FILE=processed/ai_models_merged.csv \
    MPLBACKEND=Agg
CMD ["sh", "-c", "[ -f /data/processed/ai_models_merged.csv ] || python project_infrastructures.py && python load_data.py"]