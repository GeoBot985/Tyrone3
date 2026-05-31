from app.services.document_coverage import detect_document_coverage_mode


def test_detect_document_coverage_mode_narrow_lookup():
    assert detect_document_coverage_mode("what is APO13?", "default") == "narrow_lookup"


def test_detect_document_coverage_mode_list_is_coverage_required():
    assert detect_document_coverage_mode("please list all GP consultations", "list") == "coverage_required"


def test_detect_document_coverage_mode_summary_is_coverage_required():
    assert detect_document_coverage_mode("summarize the medical deductions please", "summary") == "coverage_required"
