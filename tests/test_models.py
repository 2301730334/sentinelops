from app.extensions import db
from app.models import Scan, ScanResult, ScanStatus, User


def _user(name="alice"):
    u = User(username=name, email=f"{name}@example.com")
    u.set_password("s3cret-pass")
    db.session.add(u)
    db.session.commit()
    return u


def test_password_is_hashed(app):
    u = _user()
    assert u.password_hash != "s3cret-pass"
    assert u.check_password("s3cret-pass")
    assert not u.check_password("wrong")


def test_scan_defaults_and_serialisation(app):
    u = _user()
    scan = Scan(user_id=u.id, filename="a.csv", original_filename="a.csv")
    db.session.add(scan)
    db.session.commit()
    data = scan.to_dict()
    assert data["status"] == ScanStatus.PROCESSING
    assert data["total_rows"] == 0
    assert data["malicious_ratio"] == 0.0


def test_deleting_scan_cascades_to_results(app):
    u = _user()
    scan = Scan(user_id=u.id, filename="a.csv", original_filename="a.csv",
                total_rows=2, malicious_count=1, benign_count=1)
    db.session.add(scan)
    db.session.flush()
    db.session.add_all([
        ScanResult(scan_id=scan.id, row_index=1, label="benign", confidence=0.9, features={}),
        ScanResult(scan_id=scan.id, row_index=2, label="malicious", confidence=0.8, features={}),
    ])
    db.session.commit()
    assert scan.malicious_ratio == 0.5
    assert scan.results.count() == 2

    db.session.delete(scan)
    db.session.commit()
    assert db.session.query(ScanResult).count() == 0


def test_deleting_user_cascades_to_scans(app):
    u = _user()
    db.session.add(Scan(user_id=u.id, filename="a.csv", original_filename="a.csv"))
    db.session.commit()
    db.session.delete(u)
    db.session.commit()
    assert db.session.query(Scan).count() == 0
