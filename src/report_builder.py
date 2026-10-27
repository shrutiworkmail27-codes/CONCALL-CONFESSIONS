import html

class ReportBuilder:
    def __init__(self, template_path: str):
        with open(template_path, 'r', encoding='utf-8') as f:
            self.template = f.read()

    def _credibility_badge_class(self, credibility: str) -> str:
        if credibility in ("Exceptional", "Strong"):
            return "badge-firm"
        elif credibility == "Moderate":
            return "badge-mod"
        return "badge-severe"

    def build_single_call_section(self, result: dict) -> str:
        meta = result["metadata"]
        candor_audit = result["qa_audit"]
        guidance_records = result["guidance_records"]
        flags = result["red_flags"]
        credibility = result["credibility_rating"]
        capex_debt = result["capex_debt"]
        margin_drivers = result["margin_drivers"]

        # 1. Red Flags Table
        if flags:
            rows = ""
            for fl in flags:
                sev_badge = f'<span class="badge badge-severe">{fl["severity"]}</span>' if fl["severity"] == "Severe" else f'<span class="badge badge-mod">{fl["severity"]}</span>'
                rows += f"""<tr>
                    <td>{sev_badge}</td>
                    <td><strong>{html.escape(fl["category"])}</strong></td>
                    <td>{html.escape(fl["finding"])}</td>
                    <td style="font-family: monospace; font-size: 12px;">{html.escape(fl.get("sample", "-"))}</td>
                </tr>"""
            red_flags_html = f"""<table>
                <thead><tr><th>Severity</th><th>Category</th><th>Finding</th><th>Transcript Evidence</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>"""
        else:
            red_flags_html = "<p style='color: var(--success);'>No severe deterministic red flags or evasions detected.</p>"

        # 2. Guidance Table
        if guidance_records:
            g_rows = ""
            for g in guidance_records:
                badge_class = "badge-firm" if g["firmness"] == "Firm Commitment" else ("badge-soft" if g["firmness"] == "Hedged / Soft" else "")
                g_rows += f"""<tr>
                    <td><span class="badge {badge_class}">{html.escape(g["firmness"])}</span></td>
                    <td><strong>{html.escape(g.get("metric_category", "General"))}</strong></td>
                    <td>{", ".join(html.escape(q) for q in g["quantums"])}</td>
                    <td>{", ".join(html.escape(t) for t in g["timelines"])}</td>
                    <td style="font-size: 13px;">{html.escape(g["sentence"])}</td>
                </tr>"""
            guidance_html = f"""<table>
                <thead><tr><th>Firmness</th><th>Category</th><th>Target / Quantum</th><th>Timeline</th><th>Verbatim Statement</th></tr></thead>
                <tbody>{g_rows}</tbody>
            </table>"""
        else:
            guidance_html = "<p>No explicit numeric guidance sentences matched the target criteria.</p>"

        # 3. Deflections & Numeric Evasions
        if candor_audit.get("deflection_events"):
            d_html = ""
            for ev in candor_audit["deflection_events"]:
                ev_type = ev.get("type", "Question Deflection")
                d_html += f"""<div style="margin-bottom: 16px; border-bottom: 1px solid var(--border); padding-bottom: 12px;">
                    <div style="color: var(--danger); font-weight: 600; font-size: 13px;">[{html.escape(ev_type)}] Trigger: "{html.escape(ev['trigger_phrase'])}" — {html.escape(ev.get('speaker', 'Management'))}</div>
                    <div class="quote-box"><strong>Analyst ({html.escape(ev.get('analyst', 'Analyst'))}):</strong> {html.escape(ev['preceding_question'])}</div>
                    <div class="quote-box" style="border-left-color: var(--danger);"><strong>Management Response:</strong> {html.escape(ev['deflected_statement'])}</div>
                </div>"""
        else:
            d_html = "<p style='color: var(--success);'>Zero explicit question deflections or numeric evasions identified in Q&A session.</p>"

        # 4. Capex, Debt, and Margin Drivers
        drivers_html = "<h3>Capex & Expansion Disclosures</h3><ul>"
        if capex_debt.get("capex"):
            for c in capex_debt["capex"]:
                figs = ", ".join(html.escape(f) for f in c.get("figures", []))
                drivers_html += f"<li><strong>[{figs}]</strong> {html.escape(c['sentence'])}</li>"
        else:
            drivers_html += "<li>No explicit capex figures mentioned.</li>"
        drivers_html += "</ul>"

        drivers_html += "<h3>Debt & Working Capital Commentary</h3><ul>"
        if capex_debt.get("debt"):
            for d in capex_debt["debt"]:
                figs = ", ".join(html.escape(f) for f in d.get("figures", []))
                drivers_html += f"<li><strong>[{figs}]</strong> {html.escape(d['sentence'])}</li>"
        else:
            drivers_html += "<li>No debt or leverage figures highlighted.</li>"
        drivers_html += "</ul>"

        drivers_html += "<h3>Margin & Profitability Drivers</h3><ul>"
        if margin_drivers:
            for m in margin_drivers:
                drv = ", ".join(html.escape(d.title()) for d in m.get("drivers", []))
                figs = ", ".join(html.escape(q) for q in m.get("quantums", []))
                fig_str = f" ({figs})" if figs else ""
                drivers_html += f"<li><strong>[{drv}{fig_str}]</strong> {html.escape(m['statement'])}</li>"
        else:
            drivers_html += "<li>No specific margin driver explanations matched.</li>"
        drivers_html += "</ul>"

        return {
            "red_flags_html": red_flags_html,
            "guidance_html": guidance_html,
            "deflections_html": d_html,
            "drivers_html": drivers_html
        }

    def build_report(self, candor_audit: dict, guidance_records: list, flags: list,
                     credibility: str, capex_debt: dict, margin_drivers: list,
                     metadata: dict = None, multi_call_comparison: dict = None) -> str:
        meta = metadata or {"company": "Uploaded Transcript", "period": "Single Call Audit", "filename": "transcript"}
        single_res = {
            "metadata": meta,
            "qa_audit": candor_audit,
            "guidance_records": guidance_records,
            "red_flags": flags,
            "credibility_rating": credibility,
            "capex_debt": capex_debt,
            "margin_drivers": margin_drivers
        }
        sections = self.build_single_call_section(single_res)

        # Multi-call comparison table if 2+ transcripts were provided
        comparison_html = ""
        if multi_call_comparison and multi_call_comparison.get("calls"):
            c_rows = ""
            for c in multi_call_comparison["calls"]:
                m = c["metadata"]
                qa = c["qa_audit"]
                firm_cnt = sum(1 for g in c["guidance_records"] if g["firmness"] == "Firm Commitment")
                soft_cnt = sum(1 for g in c["guidance_records"] if g["firmness"] == "Hedged / Soft")
                b_cls = self._credibility_badge_class(c["credibility_rating"])
                c_rows += f"""<tr>
                    <td><strong>{html.escape(m['company'])}</strong> ({html.escape(m['period'])})<br><span style="font-size:11px;color:#8b949e;">{html.escape(m['filename'])}</span></td>
                    <td><strong>{qa['candor_score']} / 10</strong></td>
                    <td><span class="badge {b_cls}">{html.escape(c['credibility_rating'])}</span></td>
                    <td>{qa['deflection_rate_pct']}% ({len(qa['deflection_events'])})</td>
                    <td>{qa['hedge_density_pct']}%</td>
                    <td>{len(c['guidance_records'])} ({firm_cnt} Firm / {soft_cnt} Soft)</td>
                    <td>{len(c['red_flags'])}</td>
                </tr>"""
            comparison_html = f"""
            <div class="section">
              <h2>Multi-Concall Trajectory Comparison ({multi_call_comparison['call_count']} Calls Analyzed)</h2>
              <p style="margin-top:0;color:#8b949e;">Overall Trajectory: <strong style="color:var(--heading);">{html.escape(multi_call_comparison['trajectory'])}</strong>
              (Candor Δ: {multi_call_comparison['candor_delta']:+g} pts | Hedge Density Δ: {multi_call_comparison['hedge_delta']:+g}% | Deflection Rate Δ: {multi_call_comparison['deflect_delta']:+g}%)</p>
              <table>
                <thead><tr><th>Call / File</th><th>Candor Score</th><th>Credibility</th><th>Deflection Rate</th><th>Hedge Density</th><th>Guidance Targets</th><th>Red Flags</th></tr></thead>
                <tbody>{c_rows}</tbody>
              </table>
            </div>
            """

        rendered = self.template
        rendered = rendered.replace("{{ COMPANY_HEADER }}", html.escape(f"{meta.get('company', 'Concall')} — {meta.get('period', '')}"))
        rendered = rendered.replace("{{ CREDIBILITY_BADGE_CLASS }}", self._credibility_badge_class(credibility))
        rendered = rendered.replace("{{ CREDIBILITY_RATING }}", html.escape(credibility))
        rendered = rendered.replace("{{ CANDOR_SCORE }}", str(candor_audit["candor_score"]))
        rendered = rendered.replace("{{ DEFLECTION_RATE }}", str(candor_audit["deflection_rate_pct"]))
        rendered = rendered.replace("{{ HEDGE_DENSITY }}", str(candor_audit["hedge_density_pct"]))
        rendered = rendered.replace("{{ TARGETS_COUNT }}", str(len(guidance_records)))
        rendered = rendered.replace("{{ MULTI_CALL_SECTION }}", comparison_html)
        rendered = rendered.replace("{{ RED_FLAGS_TABLE }}", sections["red_flags_html"])
        rendered = rendered.replace("{{ GUIDANCE_TABLE }}", sections["guidance_html"])
        rendered = rendered.replace("{{ DEFLECTIONS_SECTION }}", sections["deflections_html"])
        rendered = rendered.replace("{{ DRIVERS_SECTION }}", sections["drivers_html"])

        return rendered
