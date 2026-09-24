"""Generate a password hash locally; never save or echo the plaintext password."""
from getpass import getpass
from werkzeug.security import generate_password_hash

if __name__ == '__main__':
    password = getpass('Choose an admin password (at least 12 characters): ')
    if len(password) < 12:
        raise SystemExit('Use at least 12 characters.')
    if password != getpass('Confirm password: '):
        raise SystemExit('Passwords did not match.')
    print('Copy this password hash into REWIND_ADMIN_PASSWORD_HASH in .env:')
    print(generate_password_hash(password, method='pbkdf2:sha256:1000000'))
