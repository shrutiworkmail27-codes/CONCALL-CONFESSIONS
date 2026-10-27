import json
import re

class ForensicEngine:
    """
    Forensic interrogation engine:
    - Quantifies management candor vs. defensiveness on any uploaded transcript
    - Detects explicit question deflections ("take offline") AND numeric evasions (analyst asks for numbers, management answers with zero numbers)
    - Detects guidance walk-backs, hedge density under pressure, and multi-call shifts
    - Calculates institutional scorecard ratings (/10)
    """

    NUMERIC_QUESTION_TRIGGERS = re.compile(
        r'\b(how\s+much|what\s+is\s+the|what\s+was\s+the|quantify|breakup|break-up|split|percentage|margin|capex|guidance|target|number|figure|run\s+rate|utilization)\b',
        re.IGNORECASE
    )

    NUMBER_IN_ANSWER = re.compile(
        r'(?:\b\d+(?:\.\d+)?\s*(?:%|percent|bps|cr|crore|lakh|mn|million|bn|billion|x|times)\b|(?:rs\.?|inr|₹|\$)\s*\d+)',
        re.IGNORECASE
    )

    def __init__(self, deflections_path: str, hedges_path: str, financial_path: str):
        with open(deflections_path, 'r', encoding='utf-8') as f:
            self.deflection_lexicon = json.load(f)
        with open(hedges_path, 'r', encoding='utf-8') as f:
            self.hedge_lexicon = json.load(f)
        with open(financial_path, 'r', encoding='utf-8') as f:
            self.financial_lexicon = json.load(f)

        self.all_deflections = [
            phrase for sub in self.deflection_lexicon.values() for phrase in sub
        ]
        self.all_hedges = [
            phrase for sub in self.hedge_lexicon.values() for phrase in sub
        ]

    def audit_qa_turns(self, qa_turns: list) -> dict:
        deflection_events = []
        hedged_responses = []
        numeric_evasions = []
        total_mgmt_turns = 0
        total_analyst_questions = 0
        total_mgmt_words = 0

        for i, turn in enumerate(qa_turns):
            if turn["role"] == "analyst":
                total_analyst_questions += 1
            elif turn["role"] == "management":
                total_mgmt_turns += 1
                speech = turn["text"]
                words = re.findall(r'\b\w+\b', speech.lower())
                total_mgmt_words += len(words)

                prior_question = ""
                prior_speaker = "Analyst"
                for j in range(i - 1, -1, -1):
                    if qa_turns[j]["role"] == "analyst":
                        prior_question = qa_turns[j]["text"]
                        prior_speaker = qa_turns[j]["speaker"]
                        break

                # 1. Check for explicit dodges / "take offline"
                explicit_dodge_found = False
                for dodge in self.all_deflections:
                    if re.search(r'\b' + re.escape(dodge) + r'\b', speech, re.IGNORECASE):
                        deflection_events.append({
                            "type": "Explicit Deflection / Offline Dodge",
                            "speaker": turn["speaker"],
                            "analyst": prior_speaker,
                            "trigger_phrase": dodge,
                            "deflected_statement": speech[:260] + ("..." if len(speech) > 260 else ""),
                            "preceding_question": (prior_question[:240] + ("..." if len(prior_question) > 240 else "")) if prior_question else "Opening Q&A exchange"
                        })
                        explicit_dodge_found = True
                        break

                # 2. Check for Numeric Evasion (Analyst asks quantitative question, Management gives long verbal answer with zero numbers)
                if not explicit_dodge_found and prior_question and self.NUMERIC_QUESTION_TRIGGERS.search(prior_question):
                    if not self.NUMBER_IN_ANSWER.search(speech) and len(words) >= 25:
                        numeric_evasions.append({
                            "type": "Quantitative Evasion (No Numbers Given)",
                            "speaker": turn["speaker"],
                            "analyst": prior_speaker,
                            "trigger_phrase": "Zero figures provided on quantitative query",
                            "deflected_statement": speech[:260] + ("..." if len(speech) > 260 else ""),
                            "preceding_question": prior_question[:240] + ("..." if len(prior_question) > 240 else "")
                        })

                # 3. Count hedges inside this answer
                hedges_found = [h for h in self.all_hedges if re.search(r'\b' + re.escape(h) + r'\b', speech, re.IGNORECASE)]
                if len(hedges_found) >= 2:
                    hedged_responses.append({
                        "speaker": turn["speaker"],
                        "hedge_count": len(hedges_found),
                        "hedges": hedges_found,
                        "statement": speech[:260] + ("..." if len(speech) > 260 else "")
                    })

        all_evasions = deflection_events + numeric_evasions[:5]
        hedge_density = (len(hedged_responses) / max(1, total_mgmt_turns)) * 100
        deflection_rate = (len(all_evasions) / max(1, total_mgmt_turns)) * 100

        candor_penalty = (len(deflection_events) * 1.35) + (len(numeric_evasions[:5]) * 0.65) + (hedge_density * 0.07)
        candor_score = round(max(1.0, min(10.0, 10.0 - candor_penalty)), 1)

        return {
            "candor_score": candor_score,
            "total_mgmt_turns": total_mgmt_turns,
            "total_analyst_questions": total_analyst_questions,
            "total_mgmt_words": total_mgmt_words,
            "deflection_events": all_evasions,
            "explicit_deflection_count": len(deflection_events),
            "numeric_evasion_count": len(numeric_evasions),
            "hedged_responses": hedged_responses,
            "deflection_rate_pct": round(deflection_rate, 1),
            "hedge_density_pct": round(hedge_density, 1)
        }

    def evaluate_red_flags(self, text: str, guidance_records: list, qa_audit: dict) -> list:
        flags = []

        # Red Flag 1: Question Dodging & Numeric Evasions
        total_dodges = len(qa_audit["deflection_events"])
        if total_dodges >= 2:
            flags.append({
                "severity": "Severe" if total_dodges >= 4 else "Moderate",
                "category": "Management Candor / Question Dodging",
                "finding": f"Management deflected {qa_audit['explicit_deflection_count']} inquiry(s) offline and gave {qa_audit['numeric_evasion_count']} non-numeric evasion(s) during Q&A.",
                "sample": qa_audit["deflection_events"][0]["trigger_phrase"]
            })

        # Red Flag 2: Softened / Hedged Guidance Commitments
        soft_targets = [g for g in guidance_records if g["firmness"] == "Hedged / Soft"]
        if soft_targets:
            soft_ratio = len(soft_targets) / max(1, len(guidance_records))
            flags.append({
                "severity": "Severe" if (len(soft_targets) >= 4 or soft_ratio >= 0.6) else "Moderate",
                "category": "Guidance Reliability / Soft Targets",
                "finding": f"{len(soft_targets)} of {len(guidance_records)} forward target(s) ({int(soft_ratio*100)}%) were softened with conditionality or hedge words.",
                "sample": soft_targets[0]["sentence"][:180]
            })

        # Red Flag 3: Operational Red Flag Lexicon Hits
        red_flag_hits = []
        for rf_word in self.financial_lexicon.get("red_flags", []):
            matches = re.findall(rf'([^.?!]*\b{re.escape(rf_word)}\b[^.?!]*)', text, re.IGNORECASE)
            if matches:
                red_flag_hits.append((rf_word, len(matches), matches[0].strip()))

        red_flag_hits.sort(key=lambda x: x[1], reverse=True)
        total_rf_mentions = sum(x[1] for x in red_flag_hits)
        if total_rf_mentions >= 3:
            top_terms = ", ".join(f"'{w}' ({c}x)" for w, c, _ in red_flag_hits[:4])
            flags.append({
                "severity": "Severe" if total_rf_mentions >= 8 else "Moderate",
                "category": "Operational Headwinds & Delays",
                "finding": f"Detected {total_rf_mentions} mentions of operational stress markers across transcript: {top_terms}.",
                "sample": red_flag_hits[0][2][:180]
            })

        # Red Flag 4: Working Capital / Balance Sheet Stress
        stress_hits = []
        for stress_word in self.financial_lexicon.get("balance_sheet_stress", []):
            matches = re.findall(rf'([^.?!]*\b{re.escape(stress_word)}\b[^.?!]*)', text, re.IGNORECASE)
            if len(matches) >= 3:
                stress_hits.append((stress_word, len(matches), matches[0].strip()))

        stress_hits.sort(key=lambda x: x[1], reverse=True)
        if stress_hits:
            top_w, top_c, top_s = stress_hits[0]
            flags.append({
                "severity": "Severe" if top_c >= 7 else "Moderate",
                "category": "Balance Sheet / Working Capital Focus",
                "finding": f"Elevated discussion around '{top_w}' ({top_c} mentions) and balance sheet liquidity metrics.",
                "sample": top_s[:180]
            })

        return flags

    def compute_credibility_rating(self, candor_score: float, flags: list, guidance_records: list) -> str:
        severe_count = sum(1 for f in flags if f["severity"] == "Severe")

        if candor_score >= 8.5 and severe_count == 0:
            return "Exceptional"
        elif candor_score >= 7.0 and severe_count == 0:
            return "Strong"
        elif candor_score >= 5.5 and severe_count <= 1:
            return "Moderate"
        elif candor_score >= 3.8 and severe_count <= 2:
            return "Weak"
        else:
            return "Promotional / Unreliable"

    def compare_multiple_calls(self, call_results: list) -> dict:
        """
        Compares 2 to N concall transcripts (e.g. Q1 -> Q2 -> Q3 -> Q4) to detect:
        - Candor score trajectory (improving vs. deteriorating transparency)
        - Deflection & hedge escalation under pressure
        - Guidance shifts & recurring operational red flags
        """
        if len(call_results) < 2:
            return {}

        first = call_results[0]
        last = call_results[-1]
        candor_delta = round(last["qa_audit"]["candor_score"] - first["qa_audit"]["candor_score"], 1)
        hedge_delta = round(last["qa_audit"]["hedge_density_pct"] - first["qa_audit"]["hedge_density_pct"], 1)
        deflect_delta = round(last["qa_audit"]["deflection_rate_pct"] - first["qa_audit"]["deflection_rate_pct"], 1)

        if candor_delta <= -1.0 or hedge_delta >= 10.0:
            trajectory = "Deteriorating Transparency (Rising Defensiveness)"
        elif candor_delta >= 1.0 and hedge_delta <= -5.0:
            trajectory = "Improving Candor & Execution Clarity"
        else:
            trajectory = "Stable Communication Posture"

        return {
            "call_count": len(call_results),
            "trajectory": trajectory,
            "candor_delta": candor_delta,
            "hedge_delta": hedge_delta,
            "deflect_delta": deflect_delta,
            "calls": call_results
        }
