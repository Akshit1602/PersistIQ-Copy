# Continum PersistIQ

Continum PersistIQ is a unified platform for experimentation intelligence.

## Project Structure

- `main.py`: Entry point for the interactive session.
- `core/`: Core logic (Config, LLM, State, DB).
- `data/`: Data layer (Ingestion, Synthetic Data, Medallion transforms).
- `modules/`: Analysis modules grouped by lifecycle phase.
- `utils/`: Shared statistical and reporting utilities.

## Getting Started

1. Install dependencies: `pip install -r requirements.txt`
2. Run the platform: `python main.py`
