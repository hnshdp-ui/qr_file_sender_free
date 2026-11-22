from zipfile import ZipFile

from sender.bundle import cleanup_session, create_zip
from sender.folder_scan import scan_folder


def test_nested_unicode_and_excludes_are_preserved(tmp_path):
    source = tmp_path / "My Transfer 空間"
    (source / "data" / "深い").mkdir(parents=True)
    (source / "empty").mkdir()
    (source / "data" / "深い" / "résumé.txt").write_text("hello", encoding="utf-8")
    (source / "report.xlsx").write_bytes(b"xlsx")
    (source / "~$report.xlsx").write_bytes(b"lock")
    (source / "Thumbs.db").write_bytes(b"thumb")
    (source / "notes.tmp").write_bytes(b"tmp")
    before = sorted((p.relative_to(source).as_posix(), p.stat().st_size) for p in source.rglob("*"))
    scan = scan_folder(source)
    assert scan.files == 2
    assert scan.folders == 3
    archive, session = create_zip(scan, "test-session", tmp_path)
    with ZipFile(archive) as zipped:
        assert set(zipped.namelist()) == {"data/", "data/深い/", "data/深い/résumé.txt", "empty/", "report.xlsx"}
        assert zipped.read("data/深い/résumé.txt") == b"hello"
    after = sorted((p.relative_to(source).as_posix(), p.stat().st_size) for p in source.rglob("*"))
    assert before == after
    cleanup_session(session)
    assert not session.exists()


def test_empty_directory_is_a_valid_empty_bundle(tmp_path):
    source = tmp_path / "empty"
    source.mkdir()
    scan = scan_folder(source)
    archive, session = create_zip(scan, "empty-session", tmp_path)
    with ZipFile(archive) as zipped:
        assert zipped.namelist() == []
    cleanup_session(session)
