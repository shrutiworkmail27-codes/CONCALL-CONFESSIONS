import re
import json

class ConcallExtractor:
    """
    Dynamically extracts forward-looking guidance, numbers, timelines,
    capex/debt figures, growth drivers, and margin drivers from any transcript.
    """

    TIMELINE_REGEX = re.compile(
        r"\b(?:Q[1-4]\s*(?:FY)?\s*'?\d{2,4}|FY\s*'?\d{2,4}|H[1-2]\s*(?:FY)?\s*'?\d{2,4}|(?:by|in|for)\s+20\d{2}(?:-\d{2})?|next\s+(?:quarter|year|two\s+quarters|fiscal|12\s+months)|second\s+half|first\s+half)\b",
        re.IGNORECASE
    )

    QUANTUM_REGEX = re.compile(
        r'(?:(?:Rs\.?|INR|₹|\$|€|USD)\s*[\d,]+(?:\.\d+)?\s*(?:Cr(?:ore(?:s)?)?|Lakh(?:s)?|Mn|Bn|Billion|Million|k)?|'
        r'[\d,]+(?:\.\d+)?\s*(?:\-\s*[\d,]+(?:\.\d+)?\s*)?(?:Cr(?:ore(?:s)?)?|Lakh(?:s)?|Mn|Bn|Billion|Million|bps|basis\s+points|%|percent|x\b|times\b))',
        re.IGNORECASE
    )

    INTENT_VERBS = (
        r'(?:guidance|guiding|guide|target|targeting|expect|expecting|aim|aiming|project|projecting|'
        r'estimate|estimating|aspirational|run-rate|run\s+rate|outlook|visibility|deliver|achieve|'
        r'grow\s+by|growth\s+of|revenue\s+of|margin\s+of|ebitda\s+of|pat\s+of|cagr)'
    )

    METRIC_CATEGORIES = {
        "Revenue / Top-line": ["revenue", "top line", "topline", "sales", "turnover", "order book", "inflow", "volume", "cagr"],
        "Margins / Profitability": ["margin", "ebitda", "pat", "gross", "operating", "profitability", "bps", "basis points", "roce", "roe"],
        "Capex / Capacity": ["capex", "capital expenditure", "capacity", "commissioning", "expansion", "plant", "utilization", "debottlenecking"],
        "Debt / Working Capital": ["debt", "borrowing", "leverage", "working capital", "receivable", "inventory", "cash", "repayment"]
    }

    def __init__(self, text: str, financial_lexicon_path: str = None):
        self.text = text
        self.financial_lexicon = {}
        if financial_lexicon_path:
            try:
                with open(financial_lexicon_path, 'r', encoding='utf-8') as f:
                    self.financial_lexicon = json.load(f)
            except Exception:
                self.financial_lexicon = {}
        self.sentences = self._split_into_sentences(text)

    def _split_into_sentences(self, text: str) -> list:
        clean_text = re.sub(r'\s+', ' ', text)
        # Protect common Indian/corporate abbreviations so "Rs. 500 Cr" or "Mr. Sharma" never split mid-sentence
        protected = re.sub(
            r'\b(Rs|Mr|Ms|Mrs|Dr|Prof|Sr|Jr|St|Ltd|Inc|Corp|Co|vs|etc|approx|fy|qtr)\.',
            r'\1<PRD>',
            clean_text,
            flags=re.IGNORECASE
        )
        raw_sentences = re.split(r"(?<=[.?!])\s+(?=[A-Z0-9'\"])", protected)
        return [s.replace('<PRD>', '.').strip() for s in raw_sentences if len(s.strip()) > 18]

    def _classify_metric(self, sentence: str) -> str:
        s_lower = sentence.lower()
        for category, keywords in self.METRIC_CATEGORIES.items():
            if any(k in s_lower for k in keywords):
                return category
        return "General Operational"

    def extract_guidance_commitments(self) -> list:
        guidance_records = []
        guidance_trigger = re.compile(rf'\b{self.INTENT_VERBS}\b', re.IGNORECASE)

        for sentence in self.sentences:
            if guidance_trigger.search(sentence):
                quantums = [q.strip() for q in self.QUANTUM_REGEX.findall(sentence) if q.strip()]
                timelines = [t.strip() for t in self.TIMELINE_REGEX.findall(sentence) if t.strip()]

                if quantums:
                    guidance_records.append({
                        "metric_category": self._classify_metric(sentence),
                        "sentence": sentence,
                        "quantums": list(dict.fromkeys(quantums)),
                        "timelines": list(dict.fromkeys(timelines)) if timelines else ["Ongoing / Full Year"],
                        "firmness": self._assess_sentence_firmness(sentence)
                    })

        return guidance_records

    def _assess_sentence_firmness(self, sentence: str) -> str:
        s_lower = sentence.lower()
        if any(h in s_lower for h in [
            "maybe", "subject to", "tentative", "depends", "hope", "hopefully",
            "aspirational", "roughly", "ballpark", "around", "broadly", "endeavor",
            "if all goes well", "likely", "probably", "contingent"
        ]):
            return "Hedged / Soft"
        if any(f in s_lower for f in [
            "confident", "firmly", "committed", "on track", "locked in",
            "definitely", "certainly", "assured", "visibly", "at least", "minimum"
        ]):
            return "Firm Commitment"
        return "Standard Guidance"

    def extract_capex_and_debt_commentary(self) -> dict:
        capex_mentions = []
        debt_mentions = []

        for sentence in self.sentences:
            s_lower = sentence.lower()
            quantums = [q.strip() for q in self.QUANTUM_REGEX.findall(sentence) if q.strip()]
            if any(c in s_lower for c in ["capex", "capital expenditure", "brownfield", "greenfield", "commissioning", "capacity addition"]):
                if quantums:
                    capex_mentions.append({
                        "sentence": sentence,
                        "figures": list(dict.fromkeys(quantums))
                    })
            if any(d in s_lower for d in ["debt", "borrowing", "deleverage", "repayment", "working capital", "receivable days", "interest cost"]):
                if quantums:
                    debt_mentions.append({
                        "sentence": sentence,
                        "figures": list(dict.fromkeys(quantums))
                    })

        return {
            "capex": capex_mentions,
            "debt": debt_mentions
        }

    def extract_margin_drivers(self) -> list:
        margin_findings = []
        margin_keywords = re.compile(r'\b(margin|margins|ebitda|gross margin|operating margin|profitability|spreads)\b', re.IGNORECASE)
        driver_list = self.financial_lexicon.get("margin_drivers", [
            "raw material", "operating leverage", "freight", "product mix",
            "utilization", "pricing power", "power and fuel", "realization", "input cost"
        ])
        pattern_str = r'\b(' + '|'.join(re.escape(d) for d in driver_list) + r')\b'
        driver_keywords = re.compile(pattern_str, re.IGNORECASE)

        for sentence in self.sentences:
            if margin_keywords.search(sentence) and driver_keywords.search(sentence):
                drivers_found = driver_keywords.findall(sentence)
                quantums = [q.strip() for q in self.QUANTUM_REGEX.findall(sentence) if q.strip()]
                margin_findings.append({
                    "drivers": sorted(list(set(d.lower() for d in drivers_found))),
                    "quantums": list(dict.fromkeys(quantums)),
                    "statement": sentence
                })

        return margin_findings

    def extract_growth_drivers(self) -> list:
        growth_findings = []
        growth_list = self.financial_lexicon.get("growth_drivers", [
            "commercialization", "commissioning", "order book", "order inflow",
            "client addition", "run rate", "capacity ramp", "export market", "debottlenecking"
        ])
        pattern_str = r'\b(' + '|'.join(re.escape(g) for g in growth_list) + r')\b'
        growth_keywords = re.compile(pattern_str, re.IGNORECASE)

        for sentence in self.sentences:
            if growth_keywords.search(sentence):
                drivers_found = growth_keywords.findall(sentence)
                quantums = [q.strip() for q in self.QUANTUM_REGEX.findall(sentence) if q.strip()]
                if quantums:
                    growth_findings.append({
                        "drivers": sorted(list(set(d.lower() for d in drivers_found))),
                        "quantums": list(dict.fromkeys(quantums)),
                        "statement": sentence
                    })

        return growth_findings
