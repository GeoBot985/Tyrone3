from app.services.response_format import detect_document_response_format


def test_detect_document_response_format_binary():
    assert detect_document_response_format("is there any GP consultation in here?") == "binary"


def test_detect_document_response_format_list():
    assert detect_document_response_format("please list all GP consultations") == "list"


def test_detect_document_response_format_table():
    assert detect_document_response_format("show all GP consultations with date and amount") == "table"


def test_detect_document_response_format_summary():
    assert detect_document_response_format("summarize the controls in this document") == "summary"


def test_detect_document_response_format_comparison():
    assert detect_document_response_format("compare these requirements") == "comparison"


def test_detect_document_response_format_default():
    assert detect_document_response_format("tell me about the document") == "default"
