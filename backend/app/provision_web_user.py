"""Administrator-only local command. Create/update a login and revoke its sessions."""
import argparse
import getpass
import re
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.core.database import engine
from app.core.passwords import hash_password
from app.models.web_identity import WebUser, WebSession


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--subject', required=True)
    parser.add_argument('--role', required=True, choices=['OPERATOR','PROCUREMENT_MANAGER','ADMIN'])
    parser.add_argument('--disable', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.@-]{1,128}', args.subject):
        parser.error('Use a simple username (letters, digits, dots, underscores, @ or hyphens).')
    encoded = None
    if not args.disable:
        password = getpass.getpass('New password (15–256 characters, hidden): ')
        if not 15 <= len(password) <= 256 or password != getpass.getpass('Confirm password (hidden): '):
            raise SystemExit('Password length or confirmation does not match.')
        encoded = hash_password(password)
        password = ''
    try:
        with Session(engine) as session, session.begin():
            user = session.scalar(select(WebUser).where(WebUser.subject==args.subject).with_for_update())
            if user is None:
                if args.disable:
                    raise SystemExit('User not found.')
                user = WebUser(subject=args.subject, password_hash=encoded, role=args.role)
                session.add(user)
            else:
                if encoded:
                    user.password_hash = encoded
                user.role = args.role
            user.enabled = not args.disable
            user.failed_attempts = 0
            user.locked_until = None
            session.execute(delete(WebSession).where(WebSession.subject==args.subject))
        print(f'Updated login {args.subject}. Previous browser sessions revoked. No API restart required.')
    finally:
        engine.dispose()

if __name__ == '__main__':
    main()
