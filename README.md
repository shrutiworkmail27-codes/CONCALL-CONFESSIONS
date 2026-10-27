# CONCALL-CONFESSIONS
Your company's management spent three weeks rehearsing non-answers. This offline forensic engine tears them apart in 40 milliseconds.

## Features (100% Offline • Zero APIs • Zero Pre-filled Data)
- **Dynamic Single & Multi-Concall PDF/TXT Ingestion**: Drop 1 to 4+ earnings call PDFs or text files from any company (NSE/BSE/Global) to extract live metrics on the fly.
- **Multi-Quarter Trajectory Comparison**: Automatically compares Candor Scores, Deflection Rates, Hedge Density, and Guidance Firmness across multiple concalls (`Q1.pdf Q2.pdf Q3.pdf Q4.pdf`).
- **Audited Q&A Deflections & Numeric Evasions**: Flags both explicit dodges (*"take this offline"*, *"don't have the exact figure"*) and quantitative evasions (when an analyst asks for a number/margin/split and management replies with 30+ words and zero numbers).
- **Standalone Offline Browser Studio**: Open `concall_confessions_offline_studio.html` in any browser to drag-and-drop multiple PDFs or paste transcripts directly without running terminal commands.

## CLI Usage
```bash
# Single PDF or TXT concall
python run_analysis.py company_q3_concall.pdf

# Compare 3-4 concalls across quarters
python run_analysis.py Q1_FY26.pdf Q2_FY26.pdf Q3_FY26.pdf Q4_FY26.pdf -o multi_call_autopsy.html
```
