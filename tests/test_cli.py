from metadata_grabber.cli import build_parser


def test_parser_positional_args():
    parser = build_parser()
    args = parser.parse_args(["GSE12345", "ERP67890"])
    assert args.accessions == ["GSE12345", "ERP67890"]


def test_parser_file_arg():
    parser = build_parser()
    args = parser.parse_args(["--file", "accessions.txt"])
    assert args.file == "accessions.txt"


def test_parser_output_format():
    parser = build_parser()
    args = parser.parse_args(["GSE1", "--format", "csv", "-o", "out.csv"])
    assert args.fmt == "csv"
    assert args.output == "out.csv"


def test_parser_defaults():
    parser = build_parser()
    args = parser.parse_args(["GSE1"])
    assert args.fmt == "tsv"
    assert args.output == "metadata_report.tsv"
    assert args.verbose is False
