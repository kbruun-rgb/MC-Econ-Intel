"""Converts a .pptx deck to PDF via PowerPoint COM automation (Windows +
Microsoft Office required). The PDF is cached next to the source file and
regenerated only if the source is newer, so this only costs anything on the
first request after a deck changes.
"""
import os


def ensure_pptx_pdf(pptx_path):
    """Returns the path to a PDF version of pptx_path, generating it if
    needed. Returns None if conversion isn't possible on this machine.
    """
    pdf_path = os.path.splitext(pptx_path)[0] + ".pdf"
    if os.path.isfile(pdf_path) and os.path.getmtime(pdf_path) >= os.path.getmtime(pptx_path):
        return pdf_path

    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return None

    pythoncom.CoInitialize()
    try:
        app = win32com.client.Dispatch("PowerPoint.Application")
        try:
            presentation = app.Presentations.Open(pptx_path, WithWindow=False)
            try:
                presentation.SaveAs(pdf_path, 32)  # 32 == ppSaveAsPDF
            finally:
                presentation.Close()
        finally:
            app.Quit()
    except Exception:
        return None
    finally:
        pythoncom.CoUninitialize()

    return pdf_path if os.path.isfile(pdf_path) else None
