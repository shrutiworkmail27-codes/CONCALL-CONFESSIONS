import sys
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.parser import TranscriptParser
from src.extractors import ConcallExtractor
from src.forensic_engine import ForensicEngine
from src.report_builder import ReportBuilder

def read_file(file_path: str) -> str:
    """Dynamically extracts text from any PDF or TXT concall transcript."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    if file_path.lower().endswith('.pdf'):
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(pages)
        except ImportError:
            try:
                import pdfplumber
                with pdfplumber.open(file_path) as pdf:
                    return "\n".join(p.extract_text() or "" for p in pdf.pages)
            except ImportError:
                print("[!] Neither 'pypdf' nor 'pdfplumber' is installed. Run: pip install pypdf")
                sys.exit(1)
    else:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

def analyze_single_transcript(file_path: str, engine: ForensicEngine) -> dict:
    raw_text = read_file(file_path)
    parser = TranscriptParser(raw_text, filename=file_path)
    structured = parser.get_structured_data()

    extractor = ConcallExtractor(
        raw_text,
        financial_lexicon_path=str(BASE_DIR / "lexicons" / "financial_words.json")
    )
    guidance_records = extractor.extract_guidance_commitments()
    capex_debt = extractor.extract_capex_and_debt_commentary()
    margin_drivers = extractor.extract_margin_drivers()
    growth_drivers = extractor.extract_growth_drivers()

    qa_audit = engine.audit_qa_turns(structured["qa_turns"])
    red_flags = engine.evaluate_red_flags(raw_text, guidance_records, qa_audit)
    credibility_rating = engine.compute_credibility_rating(
        qa_audit["candor_score"], red_flags, guidance_records
    )

    return {
        "metadata": structured["metadata"],
        "qa_audit": qa_audit,
        "guidance_records": guidance_records,
        "capex_debt": capex_debt,
        "margin_drivers": margin_drivers,
        "growth_drivers": growth_drivers,
        "red_flags": red_flags,
        "credibility_rating": credibility_rating
    }

def main():
    if len(sys.argv) < 2:
        print("\nUsage: python run_analysis.py <call1.pdf> [call2.pdf call3.pdf ...] [-o output_report.html]")
        print("Example (Single Call): python run_analysis.py Q3_Concall.pdf")
        print("Example (Multi-Call):  python run_analysis.py Q1.pdf Q2.pdf Q3.pdf Q4.pdf -o annual_autopsy.html\n")
        sys.exit(1)

    args = sys.argv[1:]
    output_file = "institutional_autopsy_report.html"
    input_files = []

    i = 0
    while i < len(args):
        if args[i] in ("-o", "--output") and i + 1 < len(args):
            output_file = args[i + 1]
            i += 2
        elif args[i].lower().endswith(".html") and len(args) > 1 and i == len(args) - 1:
            output_file = args[i]
            i += 1
        else:
            input_files.append(args[i])
            i += 1

    engine = ForensicEngine(
        deflections_path=str(BASE_DIR / "lexicons" / "deflection_triggers.json"),
        hedges_path=str(BASE_DIR / "lexicons" / "hedge_words.json"),
        financial_path=str(BASE_DIR / "lexicons" / "financial_words.json")
    )

    call_results = []
    for fpath in input_files:
        print(f"[*] Auditing transcript: {fpath}...")
        res = analyze_single_transcript(fpath, engine)
        call_results.append(res)
        print(f"    -> {res['metadata']['company']} ({res['metadata']['period']}): Candor {res['qa_audit']['candor_score']}/10 | {res['credibility_rating']}")

    primary = call_results[-1]
    multi_comparison = engine.compare_multiple_calls(call_results) if len(call_results) > 1 else None

    builder = ReportBuilder(str(BASE_DIR / "templates" / "report_template.html"))
    html_report = builder.build_report(
        candor_audit=primary["qa_audit"],
        guidance_records=primary["guidance_records"],
        flags=primary["red_flags"],
        credibility=primary["credibility_rating"],
        capex_debt=primary["capex_debt"],
        margin_drivers=primary["margin_drivers"],
        metadata=primary["metadata"],
        multi_call_comparison=multi_comparison
    )

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_report)

    print(f"\n[+] Offline Forensic Autopsy Complete!")
    print(f"[+] Report saved to: {output_file}\n")

if __name__ == "__main__":
    main()
