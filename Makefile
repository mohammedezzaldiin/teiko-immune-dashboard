# Teiko take-home — pipeline orchestration
.PHONY: setup pipeline dashboard test clean

# Install all dependencies (Part: Submission requirements)
setup:
	pip install -r requirements.txt

# Run the full pipeline: build DB + load data (Part 1) -> analysis (Parts 2-4).
# Regenerates teiko.db and everything under outputs/.
pipeline:
	python load_data.py
	python analysis.py

# Launch the interactive dashboard (auto-builds the DB if missing).
dashboard:
	streamlit run dashboard.py

# Optional: run the test suite.
test:
	pytest -q

clean:
	rm -f teiko.db
	rm -rf outputs/*.csv outputs/*.png
