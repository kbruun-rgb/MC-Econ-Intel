"""Add or update a client login account.

Usage:
    python create_user.py --email client@example.com --password "temp-pass" --name "Client Name"

Re-running with an existing email updates that user's name/password instead
of creating a duplicate.
"""
import argparse
import getpass

from werkzeug.security import generate_password_hash

from app import create_app, db
from app.models import User


def main():
    parser = argparse.ArgumentParser(description="Create or update a client account.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--password", help="If omitted, you'll be prompted (hidden input).")
    args = parser.parse_args()

    password = args.password or getpass.getpass("Password: ")
    email = args.email.strip().lower()

    app = create_app()
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        if user:
            user.name = args.name
            user.password_hash = generate_password_hash(password)
            action = "Updated"
        else:
            user = User(email=email, name=args.name, password_hash=generate_password_hash(password))
            db.session.add(user)
            action = "Created"
        db.session.commit()
        print(f"{action} account for {email}")


if __name__ == "__main__":
    main()
