# Catch Human Capital

## Objective

Build a functional prototype for the Catch Consulting innovation challenge.

The product transforms complex Human Capital data into:

Data
→ Analysis
→ Discovery
→ Evidence
→ Story
→ Visualization
→ Exploration

The goal is NOT to build a traditional dashboard.

The system should automatically discover relevant patterns in Human Capital
data and communicate them as understandable, evidence-based stories.

---

## Dataset

The initial dataset contains historical Human Capital survey information:

- 40 companies
- 7 bimonthly periods
- approximately 1,150 variables
- workforce
- compensation
- recruitment
- hiring
- turnover
- absenteeism
- training
- benefits
- work schedules
- internships
- social responsibility
- workforce planning

The same companies appear across multiple periods.

---

## Critical Principle

Python/statistical methods calculate the facts.

The LLM interprets and communicates those facts.

The LLM must NEVER:

- invent statistics
- modify calculated values
- invent evidence
- claim causality without methodological support

Every important narrative must be traceable to structured evidence.

---

## Architecture

src/
├── ingestion/
├── cleaning/
├── analytics/
├── findings/
├── storytelling/
└── visualization/

app/
tests/
notebooks/
docs/
config/

### ingestion
Load and understand datasets.

### cleaning
Clean and normalize data.

### analytics
Perform statistical analysis.

### findings
Represent, validate and rank discoveries.

### storytelling
Convert findings into narratives using the LLM.

### visualization
Create appropriate visualizations.

---

## Data Rules

Never modify raw data.

Raw data:
data/raw/

Processed data:
data/processed/

Data dictionaries:
data/dictionary/

Do not commit confidential or proprietary datasets to GitHub.

---

## Statistical Rules

Always distinguish:

- statistical significance
- business relevance
- correlation
- causation

Always consider sample size.

Distinguish percentages from percentage points.

Handle missing values explicitly.

---

## Development Rules

- Keep modules small.
- Avoid unnecessary dependencies.
- Prefer simple solutions.
- Do not hard-code results from the current dataset.
- Make analytical functions reusable.
- Add tests for important analytical functions.
- Do not rewrite unrelated code.
- Do not build features outside the current task.

---

## Current MVP

The MVP should eventually:

1. Load a Human Capital dataset.
2. Understand its structure.
3. Normalize relevant variables.
4. Run selected analyses.
5. Detect findings.
6. Rank findings.
7. Store supporting evidence.
8. Generate evidence-based narratives.
9. Visualize findings.
10. Allow exploration.

Start with a small reliable analytical core.

---

## Technology

Initial stack:

- Python
- Pandas
- NumPy
- SciPy
- Scikit-learn
- OpenPyXL
- Plotly
- Streamlit

Additional technologies should only be introduced when justified.

---

## Claude Code

Claude Code is a development assistant, not the product.

Before implementing a significant feature:

1. Inspect the existing code.
2. Understand the relevant interfaces.
3. Make the smallest reasonable change.
4. Run tests.
5. Verify existing functionality.

Do not implement the entire project at once.

Work on one clearly defined task at a time.
