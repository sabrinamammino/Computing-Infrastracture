import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

PROJECT_DIR   = Path(__file__).resolve().parent  # Folder of this script, so it works from any working directory.
# Inside Docker the data folder is /data (DATA_DIR is set in loader/Dockerfile).
# Run by hand, it is the data/ folder next to this script.
DATA_ROOT     = Path(os.environ["DATA_DIR"]) if os.environ.get("DATA_DIR") else PROJECT_DIR.parent / "data"
RAW_DIR       = DATA_ROOT / "raw"
PROCESSED_DIR = DATA_ROOT / "processed"
RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


# --- Source of the data  ---
KAGGLE_HANDLE = "abirambharathisa/ai-models-and-api-pricing-2026-price-history"
DATASET_VERSION = 2

EXPECTED_FILES = {
    "ai_models_2026.csv":         "f8b476200a87abc2fc3d3781aca0947dec0cd4e2b3a6ee244f7d3cad22300a9a",
    "ai_model_price_history.csv": "96cd8a317173da3f0f18bce6bfff4b67ed23fe2c46720e894ea89b1df2ca4982",
}


# SHA-256 = a "fingerprint" of a file: if even one byte changes, the fingerprint changes.
# We use it to be sure that everybody works on exactly the same data.
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:                              # "rb" = read the file as raw bytes
        for block in iter(lambda: f.read(1 << 20), b""):     # read 1 MB at a time, so big files don't fill the memory
            h.update(block)                                  # add each block to the fingerprint
    return h.hexdigest()                                     # the fingerprint as a 64-character string


# Checks that both CSV files are in data/raw/ and that they are the right version.
def raw_files_ok(verbose=True):
    """True if every expected file is in data/raw/ with the right checksum."""
    ok = True
    for name, expected in EXPECTED_FILES.items():
        path = RAW_DIR / name
        if not path.exists():                    # the file was never downloaded
            status, ok = "MISSING", False
        elif sha256(path) != expected:           # the file is there, but it is a different version (or was modified)
            status, ok = "WRONG CHECKSUM", False
        else:                                    # the file is there and it is identical to ours
            status = "OK"
        if verbose:
            print(f"  [{status}] {name}")
    return ok


# Finds the Kaggle credentials WITHOUT writing them in the notebook.
# Each of us keeps the key on their own computer (.env file or ~/.kaggle/kaggle.json),
# and these files are in .gitignore, so they never go on GitHub.
def load_credentials():
    """Read KAGGLE_USERNAME / KAGGLE_KEY from a local .env file, if there is one."""
    env_file = Path(".env")
    if env_file.exists():
        # read the .env file line by line, e.g. "KAGGLE_KEY=abc123"
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):          # skip empty lines and comments
                key, value = line.split("=", 1)                           # split name and value at the first "="
                # save it as an environment variable (only for this session, it is not saved anywhere)
                # setdefault: if the variable already exists, we don't overwrite it
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

    # kagglehub accepts the credentials in 3 ways: we check that at least one is available
    found = (os.getenv("KAGGLE_USERNAME") and os.getenv("KAGGLE_KEY")) \
            or os.getenv("KAGGLE_API_TOKEN") \
            or (Path.home() / ".kaggle" / "kaggle.json").exists()
    if not found:
        # we stop here with a clear message, instead of a confusing error from Kaggle later
        raise RuntimeError("No Kaggle credentials found: create a .env file or ~/.kaggle/kaggle.json (see above).")


# Downloads the dataset from Kaggle and puts the original CSV files in data/raw/.
def download_raw_data():
    import kagglehub  # imported here: not needed if the files are already present

    # build the dataset name: with a version number we always get the same data
    # e.g. "abirambharathisa/ai-models-and-api-pricing-2026-price-history/versions/3"
    handle = KAGGLE_HANDLE if DATASET_VERSION is None else f"{KAGGLE_HANDLE}/versions/{DATASET_VERSION}"
    if DATASET_VERSION is None:
        print("WARNING: no version pinned -> downloading the latest one.")
    print("Downloading", handle, "...")

    # kagglehub downloads the files into its own cache folder and returns the path
    folder = Path(kagglehub.dataset_download(handle, force_download=True))

    # copy our two files from the cache to data/raw/
    for name in EXPECTED_FILES:
        found = list(folder.rglob(name))          # search the file also inside subfolders
        if not found:
            raise FileNotFoundError(f"{name} is not in the downloaded dataset")
        shutil.copy2(found[0], RAW_DIR / name)   # exact copy, no changes (raw data must stay untouched)

    # small log: what we downloaded and when, saved in data/raw/download_metadata.json
    # (it contains NO credentials, only the dataset name, version, date and fingerprints)
    meta = {"kaggle_handle": KAGGLE_HANDLE, "version": DATASET_VERSION,
            "downloaded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sha256": {n: sha256(RAW_DIR / n) for n in EXPECTED_FILES}}
    (RAW_DIR / "download_metadata.json").write_text(json.dumps(meta, indent=2))

def import_local_raw_data():
    """Reuse verified CSVs supplied next to this notebook, without Kaggle access."""
    for name, expected in EXPECTED_FILES.items():
        target = RAW_DIR / name
        if target.exists():
            if sha256(target) != expected:
                raise ValueError(f"Wrong checksum: {target}. Original file was not overwritten.")
            continue
        local = PROJECT_DIR / name
        if local.is_file():
            if sha256(local) != expected:
                raise ValueError(f"Wrong checksum: {local}. File was not imported.")
            shutil.copy2(local, target)
            print(f"Imported verified local file: {name}")


import_local_raw_data()

print("Checking data/raw/ ...")
if raw_files_ok():
    print("Raw data already present and correct --> no download needed.")
else:
    
    download_raw_data()
    print("Checking the downloaded files ...")
    if not raw_files_ok():
        raise ValueError("Checksum mismatch: the Kaggle data is different from the version used in this project.")
    print("Download complete.")


models  = pd.read_csv(RAW_DIR / "ai_models_2026.csv")
history = pd.read_csv(RAW_DIR / "ai_model_price_history.csv")

print("Models file :", models.shape[0], "rows,", models.shape[1], "columns")
print("History file:", history.shape[0], "rows,", history.shape[1], "columns")


print(models.head())


print(history.head())


common = [c for c in history.columns if c in models.columns]
print("Columns in both files:", common)
print("Only in history     :", [c for c in history.columns if c not in models.columns])


print(models.dtypes)


print(history.dtypes)


models["deprecation_date"]  = pd.to_datetime(models["deprecation_date"])
models["first_listed_week"] = pd.to_datetime(models["first_listed_week"])
history["week_start"]       = pd.to_datetime(history["week_start"])

print(models[["deprecation_date", "first_listed_week"]].dtypes)
print(history[["week_start"]].dtypes)


price_cols = ["input_price_per_1m_tokens", "output_price_per_1m_tokens"]
print("Negative prices in models :", (models[price_cols] < 0).sum().sum())
print("Negative prices in history:", (history[price_cols] < 0).sum().sum())
print("Latest deprecation date   :", models["deprecation_date"].max())


print("Rows with 2098 date:", (models["deprecation_date"].dt.year > 2090).sum())
models.loc[models["deprecation_date"].dt.year > 2090, "deprecation_date"] = pd.NaT


missing_models = (models.isna().mean() * 100).round(1).sort_values(ascending=False)
print(missing_models[missing_models > 0])


missing_history = (history.isna().mean() * 100).round(1).sort_values(ascending=False)
print(missing_history[missing_history > 0])


missing_models[missing_models > 0].sort_values().plot(kind="barh", figsize=(8, 6), color="steelblue")
plt.title("Missing values in the models file (%)")
plt.xlabel("% missing")
plt.show()


print((models.groupby("mode")["input_price_per_1m_tokens"]
             .apply(lambda s: s.notna().mean() * 100)
             .round(0)
             .sort_values()))


print("Total missing in models file :", round(models.isna().sum().sum() / models.size * 100, 1), "%")
print("Total missing in history file:", round(history.isna().sum().sum() / history.size * 100, 1), "%")


print("Duplicated rows in models :", models.duplicated().sum())
print("Duplicated rows in history:", history.duplicated().sum())


print("Repeated model_id in models            :", models["model_id"].duplicated().sum())
print("Repeated (model_id + week) in history  :", history.duplicated(["model_id", "week_start"]).sum())


lower_id = models["model_id"].str.lower()
print(models[lower_id.duplicated(keep=False)][["model_id", "provider"]])


print("Rows in models file  :", len(models))
print("Different model names:", models["model_name"].nunique())
print(models["model_name"].value_counts().head(10))


print(models[["model_id", "provider", "model_name"]].sample(8, random_state=1))


print("First week:", history["week_start"].min().date())
print("Last week :", history["week_start"].max().date())
print("Number of weeks in the data:", history["week_start"].nunique())
print("Day of the week:", list(history["week_start"].dt.day_name().unique()))


all_weeks = pd.date_range(history["week_start"].min(), history["week_start"].max(), freq="W-MON")
missing_weeks = all_weeks.difference(history["week_start"].unique())
print("Weeks expected:", len(all_weeks))
print("Weeks missing :", list(missing_weeks.date))


models_per_week = history.groupby("week_start")["model_id"].nunique()
models_per_week.plot(figsize=(10, 4), color="steelblue")
plt.title("Number of models with a price, each week")
plt.ylabel("models")
plt.show()


weeks_per_model = history.groupby("model_id")["week_start"].count()
print(weeks_per_model.describe().round(0))


h = history.sort_values(["model_id", "week_start"])
previous_price = h.groupby("model_id")["input_price_per_1m_tokens"].shift()
changed = (h["input_price_per_1m_tokens"] != previous_price) & previous_price.notna()

print("Price changes found:", changed.sum())
print("% of weeks with a change:", round(changed.mean() * 100, 2), "%")


ids_models  = set(models["model_id"])
ids_history = set(history["model_id"])

print("In both files     :", len(ids_models & ids_history))
print("Only in models    :", len(ids_models - ids_history))
print("Only in history   :", len(ids_history - ids_models))


only_models = models[~models["model_id"].isin(ids_history)]
print(only_models["mode"].value_counts())


print("Types of model in the history:", list(history["mode"].unique()))


last_week = history.groupby("model_id")["week_start"].max()
only_history = last_week[~last_week.index.isin(ids_models)]

print("Still present in the last week?", (only_history == history["week_start"].max()).sum())
print(only_history.dt.year.value_counts().sort_index())


last_price = (history.sort_values("week_start")
                     .groupby("model_id")
                     .tail(1)[["model_id", "input_price_per_1m_tokens"]])

check = models.merge(last_price, on="model_id", suffixes=("_models", "_history"))
same = (check["input_price_per_1m_tokens_models"] == check["input_price_per_1m_tokens_history"]) | \
       (check["input_price_per_1m_tokens_models"].isna() & check["input_price_per_1m_tokens_history"].isna())
print("Same price:", round(same.mean() * 100, 1), "%")


descriptions = {
    "model_id": "Unique code of the model offer (model + provider). Key to join the files.",
    "model_name": "Name of the model.",
    "developer": "Company that created the model (e.g. OpenAI, Meta).",
    "developer_country": "Country of the developer.",
    "provider": "Platform that sells the model (e.g. openai, azure, openrouter).",
    "mode": "Type of model: chat, embedding, image_generation, audio_speech...",
    "input_price_per_1m_tokens": "Price in USD for 1 million input tokens.",
    "output_price_per_1m_tokens": "Price in USD for 1 million output tokens.",
    "cached_input_price_per_1m_tokens": "Price in USD for 1M cached input tokens (cheaper).",
    "batch_input_price_per_1m_tokens": "Price in USD for 1M input tokens using batch mode.",
    "batch_output_price_per_1m_tokens": "Price in USD for 1M output tokens using batch mode.",
    "price_per_image": "Price in USD per image (image models).",
    "input_price_per_second": "Price in USD per second of input (audio/video).",
    "output_price_per_second": "Price in USD per second of output (audio/video).",
    "max_input_tokens": "Maximum number of tokens the model can read.",
    "max_output_tokens": "Maximum number of tokens the model can write.",
    "supports_vision": "True if the model can read images.",
    "supports_function_calling": "True if the model can call tools/functions.",
    "supports_reasoning": "True if the model has a reasoning (thinking) mode.",
    "supports_prompt_caching": "True if the model supports prompt caching.",
    "supports_pdf_input": "True if the model can read PDF files.",
    "supports_web_search": "True if the model can search the web.",
    "supports_audio_input": "True if the model can listen to audio.",
    "supports_audio_output": "True if the model can produce audio.",
    "supports_video_input": "True if the model can watch video.",
    "supports_response_schema": "True if the model can return structured JSON.",
    "supports_computer_use": "True if the model can control a computer.",
    "supports_system_messages": "True if the model accepts system messages.",
    "deprecation_date": "Date when the model will be (or was) retired. Empty = no date.",
    "first_listed_week": "Week (Monday) when the model first appeared.",
    "source_url": "Link to the source of the price.",
    "week_start": "Week of the price observation (Monday).",
}

def make_dictionary(df, file_name):
    return pd.DataFrame({
        "file": file_name,
        "column": df.columns,
        "type": df.dtypes.astype(str).values,
        "description": [descriptions.get(c, "") for c in df.columns],
        "% missing": (df.isna().mean() * 100).round(1).values,
        "unique values": df.nunique().values,
    })

data_dictionary = pd.concat([make_dictionary(models, "ai_models_2026.csv"),
                             make_dictionary(history, "ai_model_price_history.csv")])
data_dictionary.to_csv(PROCESSED_DIR / "data_dictionary.csv", index=False)
pd.set_option("display.max_rows", 50)
pd.set_option("display.max_colwidth", 80)
print(data_dictionary)


# Columns from the models file that the history does NOT have yet
extra_cols = [c for c in models.columns if c not in history.columns]

merged = history.merge(models[["model_id"] + extra_cols], on="model_id", how="left")
merged["in_2026_list"] = merged["model_id"].isin(ids_models)

print("History rows:", len(history))
print("Merged rows :", len(merged), "(same number --> no rows lost or duplicated)")
print("Columns     :", merged.shape[1])


print(merged["in_2026_list"].value_counts())


print(merged.sample(5, random_state=0))


merged.to_csv(PROCESSED_DIR / "ai_models_merged.csv", index=False)
print("Saved:", PROCESSED_DIR / "ai_models_merged.csv")
