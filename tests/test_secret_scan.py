"""Synthetic fixtures only; never use real database credentials here."""
from scripts.check_secrets import contains_credentials


def test_detects_credentials_inside_notebook_json():
    uri = b'mongodb' + b'+srv://fixture-user:fixture-password@example.invalid/db'
    assert contains_credentials(b'{"source": ["' + uri + b'"]}')


def test_detects_percent_encoded_password():
    uri = b'mongodb' + b'://fixture-user:percent%40encoded@example.invalid/db'
    assert contains_credentials(uri)


def test_accepts_connection_without_credentials():
    assert not contains_credentials(b'mongodb://localhost:27017')
    assert not contains_credentials(b'os.environ["MONGO_URI"]')


def test_does_not_treat_query_at_sign_as_credentials():
    assert not contains_credentials(b'mongodb://localhost/db?appName=a@b')
