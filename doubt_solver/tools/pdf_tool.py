from fpdf import FPDF
import os


async def generate_pdf(title: str, content: str) -> dict:
    """Generates a PDF explanation and saves it locally.

    Use this only when the student explicitly asks for downloadable notes,
    a PDF, or something to save/print.

    Args:
        title: Short title for the PDF (used as filename and heading).
        content: The full explanation text to put in the PDF.

    Returns:
        dict with 'status' and 'filepath' of the saved PDF.
    """
    pdf = FPDF()
    pdf.add_page()
    
    # Use Unicode-compatible font
    pdf.set_font("helvetica", "B", 14)
    
    # Sanitize title and content to replace unsupported characters
    def sanitize_text(text):
        # Replace common unsupported Unicode characters with ASCII equivalents
        replacements = {
            "'": "'",  # Smart quotes
            "'": "'", 
            '"': '"',
            '"': '"',
            '—': '-',  # Em dash
            '–': '-',  # En dash
            '…': '...',  # Ellipsis
            '•': '-',  # Bullet
            '©': '(c)',  # Copyright
            '®': '(r)',  # Registered
            '™': '(tm)',  # Trademark
            # Greek letters (common in math/science)
            'α': 'alpha', 'β': 'beta', 'γ': 'gamma', 'δ': 'delta', 'ε': 'epsilon',
            'ζ': 'zeta', 'η': 'eta', 'θ': 'theta', 'ι': 'iota', 'κ': 'kappa',
            'λ': 'lambda', 'μ': 'mu', 'ν': 'nu', 'ξ': 'xi', 'ο': 'omicron',
            'π': 'pi', 'ρ': 'rho', 'σ': 'sigma', 'τ': 'tau', 'υ': 'upsilon',
            'φ': 'phi', 'χ': 'chi', 'ψ': 'psi', 'ω': 'omega',
            'Α': 'Alpha', 'Β': 'Beta', 'Γ': 'Gamma', 'Δ': 'Delta', 'Ε': 'Epsilon',
            'Ζ': 'Zeta', 'Η': 'Eta', 'Θ': 'Theta', 'Ι': 'Iota', 'Κ': 'Kappa',
            'Λ': 'Lambda', 'Μ': 'Mu', 'Ν': 'Nu', 'Ξ': 'Xi', 'Ο': 'Omicron',
            'Π': 'Pi', 'Ρ': 'Rho', 'Σ': 'Sigma', 'Τ': 'Tau', 'Υ': 'Upsilon',
            'Φ': 'Phi', 'Χ': 'Chi', 'Ψ': 'Psi', 'Ω': 'Omega',
            # Mathematical symbols
            '±': '+/-', '×': 'x', '÷': '/', '≈': 'approx', '≠': '!=', 
            '≤': '<=', '≥': '>=', '∞': 'infinity', '√': 'sqrt',
            '∑': 'sum', '∏': 'product', '∂': 'partial', '∫': 'integral',
            '°': 'deg', '²': '^2', '³': '^3',
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text
    
    safe_title = sanitize_text(title)
    safe_content = sanitize_text(content)
    
    pdf.multi_cell(0, 10, safe_title)
    pdf.ln(4)
    pdf.set_font("helvetica", size=12)
    pdf.multi_cell(0, 8, safe_content)

    # Save to local directory
    output_dir = "/tmp/mru_pdfs"
    os.makedirs(output_dir, exist_ok=True)
    
    safe_name = "".join(c if c.isalnum() else "_" for c in safe_title)[:50]
    filename = f"{safe_name}.pdf"
    filepath = os.path.join(output_dir, filename)
    
    pdf.output(filepath)
    
    return {"status": "success", "filename": filename, "filepath": filepath}
