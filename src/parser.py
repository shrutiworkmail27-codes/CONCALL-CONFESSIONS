import re
import os

class TranscriptParser:
    """
    Dynamically parses any raw earnings call transcript (PDF text or TXT):
    - Auto-detects Company Name and Quarter/Fiscal Period from header text
    - Splits Opening Management Remarks vs. Analyst Q&A Session
    - Parses speaker turns across NSE/BSE, Chorus Call, and global formats
    """

    QA_SPLIT_PATTERNS = [
        r"(?:question[ -]and[ -]answer(?:s)?\s+session)",
        r"(?:q\s*&\s*a\s+session)",
        r"(?:floor\s+is\s+open\s+for\s+questions)",
        r"(?:open\s+the\s+floor\s+for\s+q&a)",
        r"(?:we\s+will\s+now\s+begin\s+the\s+question)",
        r"(?:ladies\s+and\s+gentlemen,\s+we\s+will\s+now\s+begin)",
        r"(?:first\s+question\s+is\s+from\s+the\s+line\s+of)",
        r"(?:anyone\s+who\s+wishes\s+to\s+ask\s+a\s+question)"
    ]

    # Matches speaker headers with colon or dash: "Ramesh Iyer:", "Moderator - ", "Mr. Amit Shah (Analyst):"
    SPEAKER_PATTERN = re.compile(
        r'^(?:(?:Mr\.|Ms\.|Mrs\.|Dr\.|Shri)\s+)?[A-Z][A-Za-z\.\s\-\']{1,45}(?:\s*\([^\n\)]{1,50}\))?\s*(?::|\s+[–—-]\s+)\s*',
        re.MULTILINE
    )

    PERIOD_PATTERN = re.compile(
        r"\b(Q[1-4]\s*FY\s*'?\d{2,4}|H[1-2]\s*FY\s*'?\d{2,4}|FY\s*'?\d{2,4}|Q[1-4]\s+20\d{2})\b",
        re.IGNORECASE
    )

    COMPANY_PATTERNS = [
        re.compile(r'([A-Z][A-Za-z0-9&\s\.\-]{2,45}?\s+(?:Limited|Ltd\.?|Corporation|Corp\.?|Inc\.?|PLC|Enterprises|Industries))'),
    ]

    def __init__(self, raw_text: str, filename: str = "Transcript"):
        self.filename = filename
        self.raw_text = self._clean_text(raw_text)

    def _clean_text(self, text: str) -> str:
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = re.sub(r'Page\s+\d+\s+of\s+\d+', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def extract_metadata(self) -> dict:
        """Auto-detects company name and quarter/period from the first 2500 characters or filename."""
        header_chunk = self.raw_text[:2500]
        base_name = os.path.splitext(os.path.basename(self.filename))[0]

        # Detect Period
        period_match = self.PERIOD_PATTERN.search(header_chunk) or self.PERIOD_PATTERN.search(base_name)
        period = re.sub(r'\s+', ' ', period_match.group(1).upper()) if period_match else "Unspecified Period"

        # Detect Company
        company = None
        for pat in self.COMPANY_PATTERNS:
            matches = pat.findall(header_chunk)
            for m in matches:
                cleaned = m.strip()
                # Skip registrar / call host boilerplate names
                if not any(skip in cleaned.lower() for skip in ["chorus call", "link intime", "stock exchange", "national stock", "bombay stock", "securities and exchange"]):
                    company = cleaned
                    break
            if company:
                break

        if not company:
            company = re.sub(r'[_\-]+', ' ', base_name).strip()

        return {
            "company": company,
            "period": period,
            "filename": os.path.basename(self.filename),
            "word_count": len(re.findall(r'\b\w+\b', self.raw_text))
        }

    def split_sessions(self) -> dict:
        lower_text = self.raw_text.lower()
        split_pos = -1

        for pattern in self.QA_SPLIT_PATTERNS:
            match = re.search(pattern, lower_text)
            if match:
                split_pos = match.start()
                break

        if split_pos != -1:
            management_remarks = self.raw_text[:split_pos].strip()
            qa_session = self.raw_text[split_pos:].strip()
        else:
            # Fallback: if no explicit Q&A header, look for the first question mark after 25% of text or use 40% mark
            q_match = re.search(r'\?', self.raw_text[int(len(self.raw_text)*0.2):])
            if q_match:
                approx_pos = int(len(self.raw_text)*0.2) + max(0, q_match.start() - 300)
                management_remarks = self.raw_text[:approx_pos].strip()
                qa_session = self.raw_text[approx_pos:].strip()
            else:
                mid = int(len(self.raw_text) * 0.45)
                management_remarks = self.raw_text[:mid].strip()
                qa_session = self.raw_text[mid:].strip()

        return {
            "management_remarks": management_remarks,
            "qa_session": qa_session
        }

    def parse_qa_turns(self, qa_text: str) -> list:
        if not qa_text:
            return []

        matches = list(self.SPEAKER_PATTERN.finditer(qa_text))
        if not matches:
            return [{"speaker": "Transcript Dialogue", "role": "management", "text": qa_text}]

        dialogue = []
        for i, match in enumerate(matches):
            speaker_header = re.sub(r'(?::|\s+[–—-]\s+)\s*$', '', match.group(0).strip())
            start_idx = match.end()
            end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(qa_text)
            speech = qa_text[start_idx:end_idx].strip()
            if not speech:
                continue

            header_lower = speaker_header.lower()
            if any(term in header_lower for term in ["moderator", "operator", "host", "coordinator"]):
                role = "moderator"
            elif any(term in header_lower for term in ["analyst", "capital", "securities", "partners", "mutual fund", "asset", "equities", "broking", "wealth", "investments", "institutional"]):
                role = "analyst"
            elif any(term in header_lower for term in ["management", "md", "ceo", "cfo", "coo", "director", "chairman", "president", "vp", "head", "chief", "founder", "promoter"]):
                role = "management"
            elif "?" in speech and len(speech) < 950:
                role = "analyst"
            else:
                prev_role = dialogue[-1]["role"] if dialogue else "moderator"
                role = "management" if prev_role == "analyst" else "analyst"

            dialogue.append({
                "speaker": speaker_header,
                "role": role,
                "text": speech
            })

        return dialogue

    def get_structured_data(self) -> dict:
        metadata = self.extract_metadata()
        sessions = self.split_sessions()
        turns = self.parse_qa_turns(sessions["qa_session"])
        return {
            "metadata": metadata,
            "management_remarks": sessions["management_remarks"],
            "qa_turns": turns,
            "total_turns": len(turns)
        }
